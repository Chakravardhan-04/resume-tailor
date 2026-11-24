import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { ResumeTailorStack } from '../lib/resume-tailor-stack';

// Synthesize the stack once (with a fake frontend build) and check the CloudFormation template.
const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'dist-'));
fs.writeFileSync(path.join(dist, 'index.html'), '<html></html>');
const stack = new ResumeTailorStack(new App(), 'chakri-ResumeTailor', {
  env: { account: '123456789012', region: 'us-east-1' },
  senderEmail: 'sender@example.com',
  frontendDistPath: dist,
});
const template = Template.fromStack(stack);
const resources = (type: string) => Object.values(template.findResources(type)) as any[];

test('five prefixed Lambdas', () => {
  const names = resources('AWS::Lambda::Function').map((f) => f.Properties.FunctionName).filter(Boolean).sort();
  expect(names).toEqual(['Analyzer', 'Rewriter', 'Scorer', 'Status', 'Submit'].map((n) => `chakri_ResumeTailor_${n}`));
});

test('state machine: Analyze -> Score -> Rewrite, each with Retry and Catch', () => {
  const sm = resources('AWS::StepFunctions::StateMachine')[0];
  const json = sm.Properties.DefinitionString['Fn::Join'][1].map((p: unknown) => (typeof p === 'string' ? p : 'X')).join('');
  const { StartAt, States } = JSON.parse(json);
  expect(StartAt).toBe('Analyze');
  expect([States.Analyze.Next, States.Score.Next]).toEqual(['Score', 'Rewrite']);
  for (const name of ['Analyze', 'Score', 'Rewrite']) {
    expect(States[name].Retry.flatMap((r: any) => r.ErrorEquals)).toContain('ModelOutputError');
    expect(States[name].Catch[0].Next).toBe('MarkJobFailed');
  }
});

test('every API route needs a Cognito JWT', () => {
  for (const route of resources('AWS::ApiGatewayV2::Route')) expect(route.Properties.AuthorizationType).toBe('JWT');
});

test('only the 3 specialists can call Bedrock, only the rewriter can email', () => {
  const policies = resources('AWS::IAM::Policy').map((p) => JSON.stringify(p.Properties.PolicyDocument));
  expect(policies.filter((p) => p.includes('bedrock:InvokeModel'))).toHaveLength(3);
  expect(policies.filter((p) => p.includes('ses:SendEmail'))).toHaveLength(1);
});
