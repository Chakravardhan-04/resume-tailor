/** Settings shared by the constructs. */
export const REGION = 'us-east-1';
export const MODEL_ID = 'us.anthropic.claude-sonnet-4-6';

// AWS allows underscores in most resource names, but not in stack or S3 bucket names.
export const NAME_PREFIX = 'chakri_ResumeTailor_';
export const STACK_NAME = 'chakri-ResumeTailor';
export const BUCKET_PREFIX = 'chakri-resumetailor';
