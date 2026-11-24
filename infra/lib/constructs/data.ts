import { Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { BUCKET_PREFIX, NAME_PREFIX, RESULTS_PREFIX, UPLOADS_PREFIX } from '../config';

/** Private S3 bucket (inputs + result PDFs) and the job/audit table. */
export class Data extends Construct {
  readonly bucket: s3.Bucket;
  readonly table: dynamodb.Table;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const { account, region } = Stack.of(this);
    this.bucket = new s3.Bucket(this, 'DataBucket', {
      bucketName: `${BUCKET_PREFIX}-data-${account}-${region}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      lifecycleRules: [
        {
          id: 'expire-uploads',
          prefix: UPLOADS_PREFIX,
          expiration: Duration.days(1),
          abortIncompleteMultipartUploadAfter: Duration.days(1),
        },
        { id: 'expire-results', prefix: RESULTS_PREFIX, expiration: Duration.days(1) },
      ],
      // Demo stack: `cdk destroy` removes everything. Switch to RETAIN for real use.
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    this.table = new dynamodb.Table(this, 'JobsTable', {
      tableName: `${NAME_PREFIX}Jobs`,
      partitionKey: { name: 'jobId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'expiresAt',
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: RemovalPolicy.DESTROY,
    });
  }
}
