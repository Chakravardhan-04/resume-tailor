import * as path from 'node:path';
import { CfnOutput, Stack, StackProps, Tags } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Api } from './constructs/api';
import { Data } from './constructs/data';
import { Frontend } from './constructs/frontend';
import { Functions } from './constructs/functions';
import { Pipeline } from './constructs/pipeline';

export interface ResumeTailorStackProps extends StackProps {
  /** Built React app. Defaults to ../frontend/dist (run `npm run build` in frontend/ first). */
  frontendDistPath?: string;
}

export class ResumeTailorStack extends Stack {
  constructor(scope: Construct, id: string, props: ResumeTailorStackProps = {}) {
    super(scope, id, props);

    const data = new Data(this, 'Data');
    const functions = new Functions(this, 'Functions', { data });
    const pipeline = new Pipeline(this, 'Pipeline', { data, functions });
    const api = new Api(this, 'Api', { functions });
    const frontend = new Frontend(this, 'Frontend', {
      httpApi: api.httpApi,
      distPath: props.frontendDistPath ?? path.join(__dirname, '..', '..', 'frontend', 'dist'),
    });

    Tags.of(this).add('project', 'resume-tailor');

    new CfnOutput(this, 'SiteUrl', { value: `https://${frontend.distribution.distributionDomainName}` });
    new CfnOutput(this, 'ApiUrl', { value: api.httpApi.apiEndpoint });
    new CfnOutput(this, 'StateMachineArn', { value: pipeline.stateMachine.stateMachineArn });
    new CfnOutput(this, 'JobsTableName', { value: data.table.tableName });
    new CfnOutput(this, 'DataBucketName', { value: data.bucket.bucketName });
  }
}
