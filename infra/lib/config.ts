/** Settings shared across constructs. Keep MAX_DOC_CHARS in sync with frontend/src/limits.ts. */
export const REGION = 'us-east-1';
export const MODEL_ID = 'us.anthropic.claude-sonnet-4-6';
export const MAX_DOC_CHARS = 15000;
export const MIN_DOC_CHARS = 50;
export const MAX_AGENT_ITERATIONS = 3;
export const DOWNLOAD_URL_TTL_SECONDS = 900;

/** S3 prefixes. Objects under both expire after one day (privacy: resumes are personal data). */
export const UPLOADS_PREFIX = 'uploads/';
export const RESULTS_PREFIX = 'results/';

/** Per-user cap on jobs per UTC day (limits Bedrock cost). */
export const MAX_JOBS_PER_USER_PER_DAY = 5;

/**
 * Naming. AWS allows underscores in Lambda, DynamoDB, Step Functions, Cognito, API Gateway,
 * log group and IAM role names, but not in CloudFormation stack names or S3 bucket names,
 * which get the hyphenated, lower-case form instead.
 */
export const NAME_PREFIX = 'chakri_ResumeTailor_';
export const STACK_NAME = 'chakri-ResumeTailor';
export const BUCKET_PREFIX = 'chakri-resumetailor';
