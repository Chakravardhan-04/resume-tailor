#!/usr/bin/env bash
# Reliability demo against a deployed stack (no UI, no login needed; uses your AWS CLI credentials).
#
#   1. Forced failure: start the pipeline with the job description missing.
#      read_inputs raises InputError -> the Analyze Catch fires -> MarkJobFailed -> job FAILED with a clear message.
#   2. Length cap: call the submit Lambda with a 15,001-character resume -> 400, nothing stored or started.
#
# Usage: AWS_PROFILE=<profile> scripts/demo-reliability.sh [output-dir]
set -euo pipefail

REGION=us-east-1
STACK=chakri-ResumeTailor
OUT=${1:-}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

output() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
BUCKET=$(output DataBucketName)
TABLE=$(output JobsTableName)
SFN=$(output StateMachineArn)
SUBMIT_FN=chakri_ResumeTailor_Submit

echo "== 1. Forced failure: job description missing"
JOB=$(python3 -c "import uuid; print(uuid.uuid4())")
aws s3 cp --region "$REGION" --only-show-errors "$ROOT/docs/demo/resume.txt" "s3://$BUCKET/uploads/$JOB/resume.txt"
EXPIRES=$(( $(date +%s) + 86400 ))
aws dynamodb put-item --region "$REGION" --table-name "$TABLE" --item "{
  \"jobId\": {\"S\": \"$JOB\"}, \"sk\": {\"S\": \"META\"}, \"status\": {\"S\": \"RUNNING\"},
  \"stage\": {\"S\": \"queued\"}, \"userId\": {\"S\": \"reliability-demo\"}, \"expiresAt\": {\"N\": \"$EXPIRES\"}}"
EXEC=$(aws stepfunctions start-execution --region "$REGION" --state-machine-arn "$SFN" --name "$JOB" \
  --input "{\"jobId\":\"$JOB\",\"inputs\":{\"resume_key\":\"uploads/$JOB/resume.txt\",\"job_key\":\"uploads/$JOB/job.txt\"}}" \
  --query executionArn --output text)
echo "execution: $EXEC"

STATUS=RUNNING
for _ in $(seq 1 60); do
  STATUS=$(aws stepfunctions describe-execution --region "$REGION" --execution-arn "$EXEC" --query status --output text)
  [ "$STATUS" != RUNNING ] && break
  sleep 2
done
echo "execution status: $STATUS"

HISTORY=$(aws stepfunctions get-execution-history --region "$REGION" --execution-arn "$EXEC" --output json)
JOBITEM=$(aws dynamodb get-item --region "$REGION" --table-name "$TABLE" \
  --key "{\"jobId\":{\"S\":\"$JOB\"},\"sk\":{\"S\":\"META\"}}" --output json)
FAILURE=$(HISTORY="$HISTORY" JOBITEM="$JOBITEM" python3 - <<'PY'
import json, os
events = json.loads(os.environ["HISTORY"])["events"]
path = [e["stateEnteredEventDetails"]["name"] for e in events if e["type"].endswith("StateEntered")]
failed = next(e for e in events if e["type"] in ("LambdaFunctionFailed", "TaskFailed"))
task_failed = failed.get("lambdaFunctionFailedEventDetails") or failed["taskFailedEventDetails"]
job = json.loads(os.environ["JOBITEM"])["Item"]
summary = {
    "statesEntered": path,
    "stageError": {"error": task_failed["error"], "message": json.loads(task_failed["cause"])["errorMessage"]},
    "job": {k: job[k]["S"] for k in ("status", "stage", "errorCode", "errorMessage")},
}
print(json.dumps(summary, indent=2))
PY
)
echo "$FAILURE"

echo
echo "== 2. Length cap: 15,001-character resume"
python3 - > /tmp/length-cap-event.json <<'PY'
import json
claims = {"sub": "reliability-demo", "email": "demo@example.com", "email_verified": "true"}
body = {"resume": "x" * 15001, "jobDescription": "A job description that is long enough to pass the minimum length."}
print(json.dumps({"body": json.dumps(body), "requestContext": {"authorizer": {"jwt": {"claims": claims}}}}))
PY
aws lambda invoke --region "$REGION" --function-name "$SUBMIT_FN" --cli-binary-format raw-in-base64-out \
  --payload file:///tmp/length-cap-event.json /tmp/length-cap-response.json >/dev/null
LENGTH=$(python3 -c "import json; r=json.load(open('/tmp/length-cap-response.json')); print(json.dumps({'statusCode': r['statusCode'], 'body': json.loads(r['body'])}, indent=2))")
echo "$LENGTH"

if [ -n "$OUT" ]; then
  mkdir -p "$OUT"
  python3 - "$OUT/reliability-demo.json" <<PY
import json, sys
json.dump({"forcedFailure": json.loads('''$FAILURE'''), "lengthCap": json.loads('''$LENGTH''')}, open(sys.argv[1], "w"), indent=2)
PY
  echo "saved $OUT/reliability-demo.json"
fi
