import { execFileSync } from 'node:child_process';
import * as path from 'node:path';
import { AssetHashType, DockerImage, Duration, Stack } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import {
  DOWNLOAD_URL_TTL_SECONDS,
  MAX_AGENT_ITERATIONS,
  MAX_DOC_CHARS,
  MIN_DOC_CHARS,
  MODEL_ID,
  RESULTS_PREFIX,
  UPLOADS_PREFIX,
} from '../config';
import { Data } from './data';

const LAMBDAS_DIR = path.join(__dirname, '..', '..', '..', 'lambdas');

export interface FunctionsProps {
  data: Data;
  /** SES-verified address the results are sent from. */
  senderEmail: string;
}

/** The three specialists plus the submit and status Lambdas, each with least-privilege IAM. */
export class Functions extends Construct {
  readonly submit: lambda.Function;
  readonly status: lambda.Function;
  readonly analyzer: lambda.Function;
  readonly scorer: lambda.Function;
  readonly rewriter: lambda.Function;

  private readonly code: lambda.Code;
  private readonly layer: lambda.LayerVersion;
  private readonly baseEnv: Record<string, string>;

  constructor(scope: Construct, id: string, props: FunctionsProps) {
    super(scope, id);
    

    this.code = lambda.Code.fromAsset(path.join(LAMBDAS_DIR, 'src'), {
      exclude: ['**/__pycache__', '**/*.pyc'],
    });
    this.layer = new lambda.LayerVersion(this, 'DepsLayer', {
      description: 'reportlab (PDF generation)',
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      code: this.buildLayerCode(),
    });
    this.baseEnv = {
      DATA_BUCKET: props.data.bucket.bucketName,
      JOBS_TABLE: props.data.table.tableName,
      MODEL_ID,
      MAX_DOC_CHARS: String(MAX_DOC_CHARS),
      MIN_DOC_CHARS: String(MIN_DOC_CHARS),
      MAX_AGENT_ITERATIONS: String(MAX_AGENT_ITERATIONS),
      DOWNLOAD_URL_TTL_SECONDS: String(DOWNLOAD_URL_TTL_SECONDS),
    };

    this.status = this.fn('Status', 'status', { timeout: 10, memory: 256 });
    this.submit = this.fn('Submit', 'submit', { timeout: 30, memory: 256 });
    this.analyzer = this.fn('Analyzer', 'analyzer', { timeout: 120, memory: 512 });
    this.scorer = this.fn('Scorer', 'scorer', { timeout: 120, memory: 512 });
    this.rewriter = this.fn('Rewriter', 'rewriter', { timeout: 300, memory: 1024, layer: true });
    this.rewriter.addEnvironment('SENDER_EMAIL', props.senderEmail);

    const { bucket, table } = props.data;
    const uploads = `${UPLOADS_PREFIX}*`;
    const results = `${RESULTS_PREFIX}*`;

    bucket.grantPut(this.submit, uploads);
    table.grant(this.submit, 'dynamodb:PutItem');

    bucket.grantRead(this.status, results); // needed so presigned URLs are valid
    table.grant(this.status, 'dynamodb:GetItem');

    for (const stage of [this.analyzer, this.scorer, this.rewriter]) {
      bucket.grantRead(stage, uploads);
      table.grant(stage, 'dynamodb:UpdateItem', 'dynamodb:PutItem'); // status + audit log
      this.allowBedrock(stage);
    }
    bucket.grantPut(this.rewriter, results);
    table.grant(this.rewriter, 'dynamodb:GetItem'); // reads the recipient address
    this.allowSes(this.rewriter, props.senderEmail);
  }

  private fn(
    id: string,
    dir: string,
    opts: { timeout: number; memory: number; layer?: boolean },
  ): lambda.Function {
    return new lambda.Function(this, id, {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.X86_64,
      code: this.code,
      handler: `${dir}.handler.handler`,
      timeout: Duration.seconds(opts.timeout),
      memorySize: opts.memory,
      environment: this.baseEnv,
      layers: opts.layer ? [this.layer] : undefined,
      tracing: lambda.Tracing.ACTIVE,
      logGroup: new logs.LogGroup(this, `${id}Logs`, { retention: logs.RetentionDays.ONE_MONTH }),
    });
  }

  /** SES send, restricted to the one verified sender address. */
  private allowSes(fn: lambda.Function, senderEmail: string): void {
    const stack = Stack.of(this);
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['ses:SendEmail'],
        resources: [`arn:${stack.partition}:ses:${stack.region}:${stack.account}:identity/*`],
        conditions: { StringEquals: { 'ses:FromAddress': senderEmail } },
      }),
    );
  }

  private allowBedrock(fn: lambda.Function): void {
    const stack = Stack.of(this);
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel'],
        resources: [
          // The "us." cross-region inference profile in this account...
          `arn:${stack.partition}:bedrock:${stack.region}:${stack.account}:inference-profile/${MODEL_ID}`,
          // ...and the underlying foundation model, which the profile may route to in any US region.
          `arn:${stack.partition}:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6*`,
        ],
      }),
    );
  }

  /**
   * Installs Linux/py3.12 wheels with the local pip (no Docker needed); falls back to a
   * Docker build if local pip is unavailable.
   */
  private buildLayerCode(): lambda.Code {
    const layerDir = path.join(LAMBDAS_DIR, 'layer');
    const pipArgs = (target: string) => [
      'install',
      '-r',
      'requirements.txt',
      '-t',
      target,
      '--platform',
      'manylinux2014_x86_64',
      '--implementation',
      'cp',
      '--python-version',
      '3.12',
      '--only-binary=:all:',
      '--no-compile',
      '--quiet',
    ];
    return lambda.Code.fromAsset(layerDir, {
      assetHashType: AssetHashType.SOURCE,
      bundling: {
        image: DockerImage.fromRegistry('public.ecr.aws/sam/build-python3.12'),
        command: ['bash', '-c', `pip ${pipArgs('/asset-output/python').join(' ')}`],
        local: {
          tryBundle(outputDir: string): boolean {
            for (const python of ['python3', 'python']) {
              try {
                execFileSync(python, ['-m', 'pip', ...pipArgs(path.join(outputDir, 'python'))], {
                  cwd: layerDir,
                  stdio: 'inherit',
                });
                return true;
              } catch {
                // try the next interpreter
              }
            }
            return false;
          },
        },
      },
    });
  }
}
