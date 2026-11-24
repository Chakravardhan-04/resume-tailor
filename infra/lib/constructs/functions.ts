import { execFileSync } from 'node:child_process';
import * as path from 'node:path';
import { AssetHashType, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { MODEL_ID, NAME_PREFIX } from '../config';
import { Data } from './data';

const LAMBDAS = path.join(__dirname, '..', '..', '..', 'lambdas');

/** The five Lambdas: submit + status (API) and the three pipeline specialists. Each gets its own IAM role. */
export class Functions extends Construct {
  readonly submit: lambda.Function;
  readonly status: lambda.Function;
  readonly analyzer: lambda.Function;
  readonly scorer: lambda.Function;
  readonly rewriter: lambda.Function;

  constructor(scope: Construct, id: string, props: { data: Data; senderEmail: string }) {
    super(scope, id);
    const { bucket, table } = props.data;
    const code = lambda.Code.fromAsset(path.join(LAMBDAS, 'src'), { exclude: ['**/__pycache__'] });
    const env = { DATA_BUCKET: bucket.bucketName, JOBS_TABLE: table.tableName, MODEL_ID };

    // reportlab (PDF) as a Lambda layer, installed with local pip for Linux / Python 3.12.
    const layer = new lambda.LayerVersion(this, 'DepsLayer', {
      layerVersionName: `${NAME_PREFIX}DepsLayer`,
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      code: lambda.Code.fromAsset(path.join(LAMBDAS, 'layer'), {
        assetHashType: AssetHashType.SOURCE,
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          local: {
            tryBundle(outputDir: string) {
              execFileSync('python3', ['-m', 'pip', 'install', '-r', 'requirements.txt', '-t', path.join(outputDir, 'python'),
                '--platform', 'manylinux2014_x86_64', '--python-version', '3.12', '--only-binary=:all:', '--quiet'],
                { cwd: path.join(LAMBDAS, 'layer'), stdio: 'inherit' });
              return true;
            },
          },
        },
      }),
    });

    const fn = (name: string, handler: string, timeoutSeconds: number) =>
      new lambda.Function(this, name, {
        functionName: `${NAME_PREFIX}${name}`,
        runtime: lambda.Runtime.PYTHON_3_12,
        code,
        handler: `${handler}.handler.handler`, // e.g. analyzer/handler.py -> handler()
        timeout: Duration.seconds(timeoutSeconds),
        memorySize: 512,
        environment: env,
        layers: [layer],
        logGroup: new logs.LogGroup(this, `${name}Logs`, {
          logGroupName: `/aws/lambda/${NAME_PREFIX}${name}`,
          retention: logs.RetentionDays.ONE_MONTH,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
      });

    this.submit = fn('Submit', 'submit', 30);
    this.status = fn('Status', 'status', 10);
    this.analyzer = fn('Analyzer', 'analyzer', 120);
    this.scorer = fn('Scorer', 'scorer', 120);
    this.rewriter = fn('Rewriter', 'rewriter', 300);
    this.rewriter.addEnvironment('SENDER_EMAIL', props.senderEmail);

    // Least privilege: each function gets only what it uses.
    bucket.grantPut(this.submit, 'uploads/*');
    table.grant(this.submit, 'dynamodb:PutItem', 'dynamodb:UpdateItem'); // job record + daily quota
    bucket.grantRead(this.status, 'results/*'); // needed to sign the PDF download link
    table.grant(this.status, 'dynamodb:GetItem');

    const stack = Stack.of(this);
    for (const stage of [this.analyzer, this.scorer, this.rewriter]) {
      bucket.grantRead(stage, 'uploads/*'); // read_inputs
      table.grant(stage, 'dynamodb:PutItem', 'dynamodb:UpdateItem'); // stage progress + audit log
      // Bedrock through the IAM role (no API key). Only the three specialists may call the model.
      stage.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [
            `arn:aws:bedrock:${stack.region}:${stack.account}:inference-profile/${MODEL_ID}`,
            'arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6*', // the profile routes to any US region
          ],
        }),
      );
    }

    bucket.grantPut(this.rewriter, 'results/*'); // the PDF
    table.grant(this.rewriter, 'dynamodb:GetItem'); // reads the recipient address
    this.rewriter.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['ses:SendEmail', 'ses:SendRawEmail'], // raw MIME is needed for the PDF attachment
        resources: [`arn:aws:ses:${stack.region}:${stack.account}:identity/*`],
        conditions: { StringEquals: { 'ses:FromAddress': props.senderEmail } }, // only from our sender
      }),
    );
  }
}
