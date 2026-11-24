#!/usr/bin/env bash
# Reliability demo against the deployed stack (uses your AWS CLI credentials).
#   1. Forced failure: start the pipeline with the job description missing -> the Catch fires.
#   2. Length cap: send a 15,001-character resume to the submit Lambda -> HTTP 400.
# Usage: AWS_PROFILE=<profile> scripts/demo-reliability.sh
set -euo pipefail
export AWS_REGION=us-east-1
cd "$(dirname "$0")/.."

out() { aws cloudformation describe-stacks --stack-name chakri-ResumeTailor --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET=$(out DataBucketName); TABLE=$(out JobsTableName); SFN=$(out StateMachineArn)

echo "== 1. Forced failure: upload ONLY the resume, then start the pipeline"
JOB=$(python3 -c "import uuid; print(uuid.uuid4())")
aws s3 cp --only-show-errors docs/demo/resume.txt "s3://$BUCKET/uploads/$JOB/resume.txt"
aws dynamodb put-item --table-name "$TABLE" --item "{\"jobId\":{\"S\":\"$JOB\"},\"sk\":{\"S\":\"META\"},\"status\":{\"S\":\"RUNNING\"}}"
EXEC=$(aws stepfunctions start-execution --state-machine-arn "$SFN" --name "$JOB" --query executionArn --output text \
  --input "{\"jobId\":\"$JOB\",\"inputs\":{\"resume_key\":\"uploads/$JOB/resume.txt\",\"job_key\":\"uploads/$JOB/job.txt\"}}")

while [ "$(aws stepfunctions describe-execution --execution-arn "$EXEC" --query status --output text)" = RUNNING ]; do sleep 2; done

echo "States the execution went through:"
aws stepfunctions get-execution-history --execution-arn "$EXEC" \
  --query 'events[?stateEnteredEventDetails].stateEnteredEventDetails.name' --output text
echo "Job record (what the page shows the user):"
aws dynamodb get-item --table-name "$TABLE" --key "{\"jobId\":{\"S\":\"$JOB\"},\"sk\":{\"S\":\"META\"}}" \
  --query 'Item.{status:status.S,stage:stage.S,errorCode:errorCode.S,errorMessage:errorMessage.S}'

echo; echo "== 2. Length cap: 15,001-character resume"
python3 -c "
import json
body = {'resume': 'x' * 15001, 'jobDescription': 'A job description that is long enough to pass the minimum length.'}
claims = {'sub': 'demo', 'email': 'demo@example.com', 'email_verified': 'true'}
print(json.dumps({'body': json.dumps(body), 'requestContext': {'authorizer': {'jwt': {'claims': claims}}}}))" > /tmp/length-cap.json
aws lambda invoke --function-name chakri_ResumeTailor_Submit --cli-binary-format raw-in-base64-out \
  --payload file:///tmp/length-cap.json /tmp/length-cap-out.json >/dev/null
cat /tmp/length-cap-out.json; echo
