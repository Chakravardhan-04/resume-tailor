#!/usr/bin/env node
import 'source-map-support/register';
import { App } from 'aws-cdk-lib';
import { REGION } from '../lib/config';
import { ResumeTailorStack } from '../lib/resume-tailor-stack';

const app = new App();
new ResumeTailorStack(app, 'ResumeTailorStack', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: REGION },
  description: 'Resume-tailoring pipeline: Step Functions + Bedrock + React',
});
