import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { App } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { ResumeTailorStack } from '../lib/resume-tailor-stack';

let template: Template;

beforeAll(() => {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'dist-'));
  fs.writeFileSync(path.join(dist, 'index.html'), '<html></html>');
  const app = new App();
  const stack = new ResumeTailorStack(app, 'Test', {
    env: { account: '123456789012', region: 'us-east-1' },
    frontendDistPath: dist,
    senderEmail: 'sender@example.com',
  });
  template = Template.fromStack(stack);
});

const stateMachineDefinition = (): any => {
  const sm = Object.values(template.findResources('AWS::StepFunctions::StateMachine'))[0] as any;
  const parts = sm.Properties.DefinitionString['Fn::Join'][1] as unknown[];
  return JSON.parse(parts.map((p) => (typeof p === 'string' ? p : 'X')).join(''));
};

test('creates 5 python 3.12 functions using Bedrock-free submit/status', () => {
  const fns = Object.values(template.findResources('AWS::Lambda::Function')).filter(
    (f: any) => f.Properties.Runtime === 'python3.12' && f.Properties.Handler,
  );
  const handlers = fns.map((f: any) => f.Properties.Handler).sort();
  expect(handlers).toEqual([
    'analyzer.handler.handler',
    'rewriter.handler.handler',
    'scorer.handler.handler',
    'status.handler.handler',
    'submit.handler.handler',
  ]);
});

test('state machine chains analyze -> score -> rewrite with retry and catch', () => {
  const def = stateMachineDefinition();
  expect(def.StartAt).toBe('Analyze');
  expect(def.States.Analyze.Next).toBe('Score');
  expect(def.States.Score.Next).toBe('Rewrite');
  expect(def.States.Rewrite.End).toBe(true);
  for (const name of ['Analyze', 'Score', 'Rewrite']) {
    const state = def.States[name];
    expect(state.Retry.flatMap((r: any) => r.ErrorEquals)).toEqual(
      expect.arrayContaining(['ThrottledError', 'ModelOutputError', 'Lambda.ServiceException']),
    );
    expect(state.Catch[0].ErrorEquals).toEqual(['States.ALL']);
    expect(state.Catch[0].Next).toBe('MarkJobFailed');
  }
  expect(def.States.MarkJobFailed.Next).toBe('PipelineFailed');
  expect(def.States.PipelineFailed.Type).toBe('Fail');
});

test('state machine logs do not include execution data (resume content)', () => {
  template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
    LoggingConfiguration: Match.objectLike({ IncludeExecutionData: false, Level: 'ERROR' }),
  });
});

test('data bucket is private, encrypted, TLS-only, and expires user data', () => {
  const buckets = Object.values(template.findResources('AWS::S3::Bucket')) as any[];
  const data = buckets.find((b) => b.Properties.LifecycleConfiguration);
  expect(data.Properties.PublicAccessBlockConfiguration.BlockPublicAcls).toBe(true);
  expect(data.Properties.BucketEncryption).toBeDefined();
  const prefixes = data.Properties.LifecycleConfiguration.Rules.map((r: any) => r.Prefix);
  expect(prefixes).toEqual(expect.arrayContaining(['uploads/', 'results/']));
  template.hasResourceProperties('AWS::S3::BucketPolicy', {
    PolicyDocument: Match.objectLike({
      Statement: Match.arrayWith([
        Match.objectLike({ Condition: { Bool: { 'aws:SecureTransport': 'false' } }, Effect: 'Deny' }),
      ]),
    }),
  });
});

test('jobs table has TTL, PITR and on-demand billing', () => {
  template.hasResourceProperties('AWS::DynamoDB::Table', {
    BillingMode: 'PAY_PER_REQUEST',
    TimeToLiveSpecification: { AttributeName: 'expiresAt', Enabled: true },
    PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
    KeySchema: [
      { AttributeName: 'jobId', KeyType: 'HASH' },
      { AttributeName: 'sk', KeyType: 'RANGE' },
    ],
  });
});

test('every API route requires the Cognito JWT authorizer', () => {
  const routes = Object.values(template.findResources('AWS::ApiGatewayV2::Route')) as any[];
  expect(routes.length).toBe(2);
  for (const r of routes) {
    expect(r.Properties.AuthorizationType).toBe('JWT');
    expect(r.Properties.AuthorizerId).toBeDefined();
  }
  template.hasResourceProperties('AWS::ApiGatewayV2::Authorizer', {
    AuthorizerType: 'JWT',
    JwtConfiguration: Match.objectLike({ Audience: [Match.anyValue()] }),
  });
});

test('user pool: email sign-in, verified email, public client without secret', () => {
  template.hasResourceProperties('AWS::Cognito::UserPool', {
    UsernameAttributes: ['email'],
    AutoVerifiedAttributes: ['email'],
    Policies: Match.objectLike({ PasswordPolicy: Match.objectLike({ MinimumLength: 10 }) }),
  });
  template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
    GenerateSecret: false,
    ExplicitAuthFlows: Match.arrayWith(['ALLOW_USER_PASSWORD_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH']),
    PreventUserExistenceErrors: 'ENABLED',
  });
});

test('api exposes only submit and status routes, with throttling', () => {
  const routes = Object.values(template.findResources('AWS::ApiGatewayV2::Route')).map(
    (r: any) => r.Properties.RouteKey,
  );
  expect(routes.sort()).toEqual(['GET /api/jobs/{jobId}', 'POST /api/submit']);
  template.hasResourceProperties('AWS::ApiGatewayV2::Stage', {
    RouteSettings: { 'POST /api/submit': { ThrottlingRateLimit: 1, ThrottlingBurstLimit: 3 } },
  });
});

test('cloudfront forwards /api/* to the API and has no SPA error rewrite', () => {
  template.hasResourceProperties('AWS::CloudFront::Distribution', {
    DistributionConfig: Match.objectLike({
      CacheBehaviors: Match.arrayWith([Match.objectLike({ PathPattern: '/api/*' })]),
      DefaultRootObject: 'index.html',
    }),
  });
  const dist = Object.values(template.findResources('AWS::CloudFront::Distribution'))[0] as any;
  expect(dist.Properties.DistributionConfig.CustomErrorResponses).toBeUndefined();
});

test('only the three stage functions may invoke Bedrock', () => {
  const policies = Object.values(template.findResources('AWS::IAM::Policy')) as any[];
  const withBedrock = policies.filter((p) =>
    JSON.stringify(p.Properties.PolicyDocument).includes('bedrock:InvokeModel'),
  );
  expect(withBedrock).toHaveLength(3);
});

test('submit can update the quota counter', () => {
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  expect(policies).toContain('dynamodb:UpdateItem');
});

test('submit can start the state machine; no function has wildcard actions', () => {
  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: Match.objectLike({
      Statement: Match.arrayWith([Match.objectLike({ Action: 'states:StartExecution' })]),
    }),
  });
  const json = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  expect(json).not.toMatch(/"Action":"\*"/);
});

test('only the rewriter can send email, and only from the configured sender', () => {
  const policies = Object.values(template.findResources('AWS::IAM::Policy')) as any[];
  const withSes = policies.filter((p) => JSON.stringify(p.Properties.PolicyDocument).includes('ses:SendEmail'));
  expect(withSes).toHaveLength(1);
  const statement = withSes[0].Properties.PolicyDocument.Statement.find((s: any) => s.Action === 'ses:SendEmail');
  expect(statement.Condition).toEqual({ StringEquals: { 'ses:FromAddress': 'sender@example.com' } });
  expect(JSON.stringify(statement.Resource)).toContain(':identity/*');
  template.hasResourceProperties('AWS::Lambda::Function', {
    Handler: 'rewriter.handler.handler',
    Environment: { Variables: Match.objectLike({ SENDER_EMAIL: 'sender@example.com' }) },
  });
});
