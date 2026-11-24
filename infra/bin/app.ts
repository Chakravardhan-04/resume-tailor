#!/usr/bin/env node
import 'source-map-support/register';
import { App } from 'aws-cdk-lib';
import { REGION } from '../lib/config';
import { ResumeTailorStack } from '../lib/resume-tailor-stack';

const app = new App();
const senderEmail = app.node.tryGetContext('senderEmail') as string | undefined;
if (!senderEmail || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(senderEmail)) {
  throw new Error(
    'Pass a valid SES sender address: cdk deploy -c senderEmail=you@example.com (it must be verified in SES, us-east-1).',
  );
}
new ResumeTailorStack(app, 'ResumeTailorStack', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: REGION },
  senderEmail,
  description: 'Resume-tailoring pipeline: Step Functions + Bedrock + React',
});
