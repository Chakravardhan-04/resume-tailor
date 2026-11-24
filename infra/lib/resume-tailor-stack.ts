import * as path from 'node:path';
import { Aspects, CfnOutput, IAspect, Names, Stack, StackProps, Tags, Token } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct, IConstruct } from 'constructs';
import { Api } from './constructs/api';
import { Auth } from './constructs/auth';
import { Data } from './constructs/data';
import { Frontend } from './constructs/frontend';
import { Functions } from './constructs/functions';
import { Pipeline } from './constructs/pipeline';
import { NAME_PREFIX } from './config';

/** Gives every IAM role we create a readable, prefixed name (<= 64 chars, unique per construct path). */
class PrefixRoleNames implements IAspect {
  visit(node: IConstruct): void {
    // L2 roles carry an unresolved placeholder when no name was given; we never set explicit names.
    if (node instanceof iam.CfnRole && (node.roleName === undefined || Token.isUnresolved(node.roleName))) {
      // e.g. chakri_ResumeTailor_Functions_Analyzer_ServiceRole_1A2B3C4D
      const base = node.node.scopes
        .slice(2) // skip app and stack
        .map((c) => c.node.id)
        .filter((id) => id && id !== 'Resource')
        .join('_')
        .replace(/[^A-Za-z0-9_+=,.@-]/g, '');
      const hash = Names.uniqueId(node).slice(-8);
      const room = 64 - NAME_PREFIX.length - hash.length - 1;
      node.roleName = `${NAME_PREFIX}${base.slice(0, room)}_${hash}`;
    }
  }
}

export interface ResumeTailorStackProps extends StackProps {
  /** SES-verified sender address (deploy with `-c senderEmail=you@example.com`). */
  senderEmail: string;
  /** Built React app. Defaults to ../frontend/dist (run `npm run build` in frontend/ first). */
  frontendDistPath?: string;
}

export class ResumeTailorStack extends Stack {
  constructor(scope: Construct, id: string, props: ResumeTailorStackProps) {
    super(scope, id, props);

    const data = new Data(this, 'Data');
    const functions = new Functions(this, 'Functions', { data, senderEmail: props.senderEmail });
    const pipeline = new Pipeline(this, 'Pipeline', { data, functions });
    const auth = new Auth(this, 'Auth');
    const api = new Api(this, 'Api', { functions, auth });
    const frontend = new Frontend(this, 'Frontend', {
      httpApi: api.httpApi,
      auth,
      distPath: props.frontendDistPath ?? path.join(__dirname, '..', '..', 'frontend', 'dist'),
    });

    Aspects.of(this).add(new PrefixRoleNames());
    Tags.of(this).add('project', 'chakri_ResumeTailor');

    new CfnOutput(this, 'SiteUrl', { value: `https://${frontend.distribution.distributionDomainName}` });
    new CfnOutput(this, 'UserPoolId', { value: auth.userPool.userPoolId });
    new CfnOutput(this, 'UserPoolClientId', { value: auth.client.userPoolClientId });
    new CfnOutput(this, 'ApiUrl', { value: api.httpApi.apiEndpoint });
    new CfnOutput(this, 'StateMachineArn', { value: pipeline.stateMachine.stateMachineArn });
    new CfnOutput(this, 'JobsTableName', { value: data.table.tableName });
    new CfnOutput(this, 'DataBucketName', { value: data.bucket.bucketName });
  }
}
