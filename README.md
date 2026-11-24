# Resume Tailor

[![CI](https://github.com/Chakravardhan-04/resume-tailor/actions/workflows/ci.yml/badge.svg)](https://github.com/Chakravardhan-04/resume-tailor/actions/workflows/ci.yml)

A multi-agent AWS pipeline that tailors a resume to a job description. Three specialist Lambdas, chained by Step Functions and powered by Claude on Amazon Bedrock, return:

- a tailored summary and bullet points, written **only from facts in the original resume**
- an honest **gap list** of requirements the resume does not meet yet
- a **PDF** to download, and the same draft **emailed** through Amazon SES

**Live demo:** https://d3a7a5yx4axqt.cloudfront.net (sign-up required, demo use only)

![Result page](docs/demo/screenshots/04-result.png)

## Contents

1. [Architecture](#architecture)
2. [How the pipeline works](#how-the-pipeline-works)
3. [Honesty guardrail](#honesty-guardrail)
4. [Reliability and security](#reliability-and-security)
5. [Tech stack](#tech-stack)
6. [Repository layout](#repository-layout)
7. [Setup (local development)](#setup-local-development)
8. [Deploy to AWS](#deploy-to-aws)
9. [Demo](#demo)
10. [Audit log: all 3 stages](#audit-log-all-3-stages)
11. [GitHub](#github)
12. [Known limitations](#known-limitations)
13. [Spec exit check](#spec-exit-check)

## Architecture

```mermaid
flowchart LR
  U[Browser<br/>React + Vite] -->|sign in| COG[Cognito<br/>user pool]
  U -->|HTTPS + ID token| CF[CloudFront]
  CF -->|/* static| S3W[(S3 site bucket<br/>private, OAC)]
  CF -->|/api/*| APIGW[API Gateway<br/>HTTP API<br/>JWT authorizer]
  APIGW -.->|validate token| COG
  APIGW -->|POST /api/submit| SUB[submit λ]
  APIGW -->|GET /api/jobs/id| STA[status λ]
  SUB -->|resume + JD| S3D[(S3 data bucket<br/>uploads/ results/)]
  SUB -->|job RUNNING| DDB[(DynamoDB<br/>jobs + audit log)]
  SUB -->|start| SFN

  subgraph SFN[Step Functions state machine]
    direction LR
    A[analyzer λ] --> B[scorer λ] --> C[rewriter λ]
  end

  A & B & C -->|converse| BR[Bedrock<br/>Claude Sonnet 4.6]
  A & B & C -->|audit entry| DDB
  C -->|PDF| S3D
  C -->|email + PDF| SES[SES]
  STA --> DDB
  STA -->|presigned URL| S3D
```

CloudFront serves the React app and forwards `/api/*` to the API, so the browser stays on one origin and no CORS configuration is needed.

### State machine

```mermaid
stateDiagram-v2
  [*] --> Analyze
  Analyze --> Score: $.analysis
  Score --> Rewrite: $.match
  Rewrite --> [*]: $.rewrite
  Analyze --> MarkJobFailed: Catch
  Score --> MarkJobFailed: Catch
  Rewrite --> MarkJobFailed: Catch
  MarkJobFailed --> PipelineFailed
  PipelineFailed --> [*]
  note right of Analyze
    Each stage: Retry on ThrottledError, ModelOutputError
    and Lambda service errors (backoff + jitter)
  end note
```

## How the pipeline works

1. **Sign in.** The user creates an account with email and password, confirms the emailed code, and signs in. The browser keeps the Cognito ID token in `sessionStorage`.
2. **Submit.** The page posts the resume and job description to `POST /api/submit`. API Gateway rejects requests without a valid token. The submit Lambda takes the user id and verified email from the token claims (never from the request body), enforces 5 jobs per user per day, validates both documents, stores them in S3, creates the job in DynamoDB, starts the state machine, and returns a job id immediately. This avoids the 29 second API Gateway timeout.
3. **Three specialists** run in order. The state object is the pipeline's memory: each stage's output is carried forward at `$.analysis`, `$.match` and `$.rewrite`.

   | Stage | Reads | Produces | Focus |
   |---|---|---|---|
   | `analyzer` | job description (via the `read_inputs` tool) | requirements, each `must_have` or `nice_to_have` | extract only what the posting states |
   | `scorer` | resume + requirements | matches with verbatim evidence, gaps with reasons, score 0-100 | judge only on evidence in the resume |
   | `rewriter` | resume + matches + gaps | summary, bullets, PDF, email | reword existing facts, never invent |

   The score is computed in code: `must_have` counts double, and a match only counts if its evidence quote really exists in the resume.
4. **Deliver.** The rewriter stores the PDF, emails the draft and gap list with the PDF attached, deletes the stored recipient address, and marks the job done. An email failure never fails the job.
5. **Poll.** The page calls `GET /api/jobs/{id}` every 3 seconds. When the job is done, it renders the result, the email outcome and a fresh 15 minute presigned PDF link. Users can only read their own jobs.

## Honesty guardrail

The rewriter must never fabricate experience, skills or credentials. The prompt is only the first of five layers. Layers 2 to 4 are deterministic code, so they hold even if the model ignores its instructions.

| # | Layer | Code |
|---|---|---|
| 1 | Prompt rules: gaps are passed as "do not mention or imply"; no new numbers, outcomes, scope or skill-level claims | `common/prompts.py` |
| 2 | Every bullet must cite a `source_quote` that exists verbatim in the resume | `guardrails.quote_in_source` |
| 3 | A number that is not in the resume drops the bullet or summary | `guardrails.numbers_supported` |
| 4 | Claim words such as "production", "managed", "led", "expert", "improving" are only allowed if the resume uses them | `guardrails.unsupported_claims` |
| 5 | A separate verifier call fact-checks the surviving draft and flags unsupported bullets | `rewriter.verify` |

Rejected content is fed back to the model (for example, "do not use these words: production, managed"), within a bounded loop. If nothing honest survives, the job fails with a clear message instead of returning invented content. Unmet requirements always appear in the gap list. In the [demo run](#audit-log-all-3-stages) the first draft had 3 bullets rejected; the second attempt kept 5 honest bullets.

## Reliability and security

| Pattern | Implementation |
|---|---|
| Max iterations | `llm.converse_json` repairs invalid JSON at most `MAX_AGENT_ITERATIONS` (3) times. The rewriter's generate, filter and verify loop has the same cap. |
| Error recovery | Step Functions `Retry` with backoff and jitter on `ThrottledError`, `ModelOutputError` and Lambda service errors. `Catch` marks the job `FAILED`, keeping the clearest message. A missing document raises `InputError` with a user-facing message. |
| Input guardrails | 50 to 15,000 characters per document, checked in the browser, the submit Lambda and the analyzer. Documents are wrapped as untrusted data in every prompt. |
| Output guardrails | AWS keys, tokens, private keys and JWTs are redacted from results, emails and audit entries. |
| Audit log | Every stage writes its output to DynamoDB under `jobId` + `AUDIT#<timestamp>#<stage>`. |
| Access control | Cognito JWT on every route, job ownership check, 5 jobs per user per day, API throttling (submit: 1 req/s, burst 3). |
| Least privilege | One IAM role per Lambda. Only the three stages can call Bedrock. Only the rewriter can send email, and only from the configured sender. |
| Privacy | S3 objects expire after 1 day, DynamoDB records after 30 days. The recipient address is deleted after sending. Step Functions logs errors only, without execution data. |
| Web security | Private S3 behind CloudFront (OAC), HTTPS only, CSP, HSTS, `X-Frame-Options: DENY`, no third-party scripts or fonts. |

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, TypeScript, plain CSS with design tokens (light and dark), Vitest + Testing Library, oxlint |
| Backend | Python 3.12 Lambdas, boto3, reportlab (PDF), ruff, pytest |
| Orchestration | AWS Step Functions (Standard) |
| LLM | Amazon Bedrock `converse()`, `us.anthropic.claude-sonnet-4-6`, us-east-1, IAM role only (no API key) |
| Auth | Amazon Cognito user pool, API Gateway JWT authorizer |
| API | API Gateway HTTP API |
| Email | Amazon SES v2 (raw MIME with PDF attachment) |
| Storage | S3 (private, encrypted), DynamoDB (on demand, TTL, PITR) |
| Hosting | S3 + CloudFront |
| IaC | AWS CDK v2 (TypeScript) with jest assertions |
| CI | GitHub Actions, Dependabot |

## Repository layout

```
.
├── frontend/                 React app
│   └── src/
│       ├── auth/             Cognito client, auth context and provider
│       ├── components/       layout (header, footer) and ui (button, alert, spinner, ...)
│       ├── features/
│       │   ├── auth/         sign-in, sign-up, email confirmation
│       │   └── tailor/       input form, progress, result view, score ring
│       ├── hooks/            usePollJob
│       └── styles/           design tokens and styles
├── lambdas/
│   ├── src/
│   │   ├── common/           config, errors, guardrails, llm, prompts, storage, jobs, mailer, pdf, http, stage
│   │   ├── analyzer/  scorer/  rewriter/     Step Functions stages
│   │   └── submit/  status/                  API handlers
│   ├── tests/                pytest suite (no AWS calls)
│   └── layer/requirements.txt
├── infra/                    CDK app
│   ├── lib/constructs/       data, auth, functions, pipeline, api, frontend
│   └── test/                 template assertions
├── docs/demo/                screenshots, sample inputs, result, PDF and audit log from a real run
└── .github/                  CI workflow, Dependabot
```

## Setup (local development)

Prerequisites: Node 22+, Python 3.12+ with pip, and (for deploying) the AWS CLI.

```bash
git clone https://github.com/Chakravardhan-04/resume-tailor.git
cd resume-tailor
```

**Lambdas**

```bash
cd lambdas
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
```

**Frontend**

```bash
cd frontend
npm ci
npm run lint && npm run typecheck && npm test && npm run build
```

To run the UI locally against a deployed stack:

```bash
cp public/config.example.json public/config.json      # fill in UserPoolId and UserPoolClientId from the stack outputs
VITE_API_PROXY=https://<api-id>.execute-api.us-east-1.amazonaws.com npm run dev
```

**Infra**

```bash
cd infra
npm ci
npm test
npx cdk synth -c senderEmail=you@example.com     # needs frontend/dist (run the frontend build first)
```

Unit tests never call AWS: a pytest fixture blocks the DynamoDB, S3, SES and Bedrock clients.

## Deploy to AWS

1. **Enable Claude Sonnet 4.6 in Bedrock** (us-east-1). First-time Anthropic users must submit the use-case form once (Bedrock console, Model catalog, Anthropic). Check:
   ```bash
   aws bedrock get-foundation-model-availability --region us-east-1 --model-id anthropic.claude-sonnet-4-6
   ```
   `authorizationStatus` must be `AUTHORIZED`.
2. **Verify the SES sender**, then click the link SES emails you:
   ```bash
   aws sesv2 create-email-identity --region us-east-1 --email-identity you@example.com
   ```
   In SES sandbox mode, recipients must be verified too. Users only ever receive mail at their own verified account address, so requesting SES production access is safe once you need it.
3. **Bootstrap CDK** once per account and region:
   ```bash
   cd infra && npm ci
   npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
   ```
4. **Build the frontend**:
   ```bash
   cd frontend && npm ci && npm run build
   ```
5. **Deploy** (one command for the whole stack):
   ```bash
   cd infra && npx cdk deploy -c senderEmail=you@example.com
   ```
   Use `--profile <name>` or `AWS_PROFILE` to pick the account.

| Output | Use |
|---|---|
| `SiteUrl` | the app |
| `ApiUrl` | API Gateway endpoint (for local dev proxy) |
| `UserPoolId`, `UserPoolClientId` | local `config.json` |
| `JobsTableName` | audit log export |
| `StateMachineArn`, `DataBucketName` | debugging |

6. **First use:** open `SiteUrl`, choose **Create an account**, enter the emailed code, sign in, and click **Try a sample**.

**Updating:** rebuild the frontend if it changed, then run the same `cdk deploy`.

**Clean up:**
```bash
cd infra && npx cdk destroy -c senderEmail=you@example.com
```
Buckets are emptied, and the table and user pool are deleted (`RemovalPolicy.DESTROY`, demo setting). The CDK bootstrap stack is left in place.

### Resource names

Resources are prefixed `chakri_ResumeTailor_`, for example `chakri_ResumeTailor_Analyzer`, `chakri_ResumeTailor_Jobs`, `chakri_ResumeTailor_Pipeline`, `chakri_ResumeTailor_Users`. AWS does not allow underscores in CloudFormation stack names or S3 bucket names, so those are `chakri-ResumeTailor` and `chakri-resumetailor-{data,site}-<account>-<region>`. Two internal CDK helpers keep generated names. Everything is tagged `project=chakri_ResumeTailor`.

### Troubleshooting

**`TimeoutError ... did not establish a connection within 10000 ms` during deploy.** Some networks stall on IPv6 (AAAA) DNS lookups, so Node needs about 15 seconds per AWS hostname. Force IPv4 lookups for the deploy only:

```bash
cat > /tmp/ipv4-dns.cjs <<'JS'
const dns = require('node:dns'); const orig = dns.lookup;
dns.lookup = (h, o, cb) => { if (typeof o === 'function') { cb = o; o = {}; } else if (typeof o === 'number') { o = { family: o }; } else { o = { ...(o || {}) }; }
  if (!o.family) o.family = 4; return orig.call(dns, h, o, cb); };
JS
NODE_OPTIONS="--require /tmp/ipv4-dns.cjs" npx cdk deploy -c senderEmail=you@example.com
```

**Every job fails with `Operation not allowed`.** Bedrock access to Anthropic models is not enabled (deploy step 1).

**"Email not sent" on the result page.** The sender or recipient is not verified in SES, or the account is in sandbox mode. The PDF download still works.

## Demo

A real run on the deployed stack, using the fictional sample from **Try a sample**. Inputs and outputs are in [`docs/demo/`](docs/demo). The account email is redacted in the screenshots.

| Step | Screenshot |
|---|---|
| 1. Sign in or create an account | ![Sign in](docs/demo/screenshots/01-sign-in.png) |
| 2. Paste or upload the resume and job description | ![Form](docs/demo/screenshots/02-tailor-form.png) |
| 3. Watch the three stages run | ![Processing](docs/demo/screenshots/03-processing.png) |
| 4. Score, tailored draft, gap list, evidence, PDF and email confirmation | ![Result](docs/demo/screenshots/04-result.png) |

Mobile layout: [`05-result-mobile.png`](docs/demo/screenshots/05-result-mobile.png). Files from the run:

- [`resume.txt`](docs/demo/resume.txt) and [`job-description.txt`](docs/demo/job-description.txt): inputs
- [`result.json`](docs/demo/result.json): the status API response (email status `SENT`)
- [`tailored-resume.pdf`](docs/demo/tailored-resume.pdf): the generated PDF, also attached to the email
- [`audit-log.json`](docs/demo/audit-log.json): the audit log described below

Outcome: score **67/100**, 5 of 9 requirements matched, 5 tailored bullets, 4 gaps (Terraform/CDK is the missing must-have, because the resume only mentions AWS SAM). The whole pipeline took about 16 seconds.

## Audit log: all 3 stages

Each stage writes its full output to the jobs table. The demo job `cdc641ec-c629-43cf-b79c-02db6eeb811f` has one entry per stage:

| Sort key | Stage | Recorded output |
|---|---|---|
| `AUDIT#2026-11-24T14:16:30.040+00:00#analyzer` | analyzer | 9 requirements (6 must have, 3 nice to have) |
| `AUDIT#2026-11-24T14:16:34.431+00:00#scorer` | scorer | score 67, 5 matches with evidence, 4 gaps with reasons |
| `AUDIT#2026-11-24T14:16:45.718+00:00#rewriter` | rewriter | final summary, bullets and gaps, PDF key, `emailStatus: SENT` |

Excerpts from [`docs/demo/audit-log.json`](docs/demo/audit-log.json):

```jsonc
// analyzer
{"requirements": [
  {"id": "R1", "text": "3+ years of professional experience in backend development", "category": "must_have", "type": "experience"},
  {"id": "R2", "text": "Strong Python skills", "category": "must_have", "type": "skill"},
  // ... 9 in total
]}

// scorer
{"score": 67,
 "matched": [{"id": "R1", "requirement": "3+ years of professional experience in backend development", "category": "must_have",
              "evidence": "Backend-focused software engineer with 3 years of experience building Python services and REST APIs on AWS."}],
 "gaps":    [{"id": "R5", "requirement": "Infrastructure as code with Terraform or AWS CDK", "category": "must_have",
              "reason": "No mention of Terraform or AWS CDK; AWS SAM is referenced but neither Terraform nor CDK appears in the resume."}]}

// rewriter
{"resultKey": "results/cdc641ec-c629-43cf-b79c-02db6eeb811f.pdf",
 "emailStatus": "SENT",
 "result": {"score": 67, "summary": "Backend-focused software engineer with 3 years of experience ...",
            "bullets": ["Built REST APIs in Python and Flask for an order management system, serving 40,000 requests per day.", "..."],
            "gaps": ["..."], "matched": ["..."]}}
```

The rewriter's CloudWatch log for the same job shows the guardrail loop: `attempt=1 kept=3 dropped=3`, then `attempt=2 kept=5 dropped=1`.

Export the audit log for any job:

```bash
aws dynamodb query --region us-east-1 --table-name chakri_ResumeTailor_Jobs \
  --key-condition-expression "jobId = :j AND begins_with(sk, :a)" \
  --expression-attribute-values '{":j":{"S":"<jobId>"},":a":{"S":"AUDIT#"}}' > audit-export.json
```

## GitHub

Repository: https://github.com/Chakravardhan-04/resume-tailor

**CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push to `main` and on every pull request:

| Job | Checks |
|---|---|
| Lambdas | `ruff check`, `ruff format --check`, `pytest` |
| Frontend | `oxlint`, `tsc`, `vitest`, `vite build` (uploads `dist` for the next job) |
| Infra | `tsc`, `jest` template assertions, `cdk synth` (no AWS credentials needed) |

**Dependabot** opens weekly update PRs for npm (frontend, infra), pip (Lambda layer) and GitHub Actions. Merge them only when CI is green, and check major versions by hand (for example, ts-jest does not support TypeScript 7 yet).

**Conventions.** Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `docs:`, `ci:`, `chore:`). Work on a branch, open a pull request, and merge when CI passes. No secrets are stored in the repo: the app uses IAM roles, and the frontend config holds only public Cognito identifiers.

## Known limitations

- Self sign-up is open. Daily limits and throttling cap Bedrock cost per user, but not the number of accounts. Add an AWS Budgets alarm, and consider invite-only sign-up or AWS WAF.
- Password reset and MFA are not implemented. Cognito's default email sender allows about 50 verification emails per day; configure Cognito to use SES for more.
- Input is plain text or a `.txt` / `.md` file. PDF and DOCX parsing is not implemented.
- The API Gateway endpoint can also be called directly (still authenticated). CloudFront uses its default certificate, so the minimum TLS version is fixed at TLSv1 until a custom domain and ACM certificate are added.
- Prompt injection inside a document cannot be ruled out entirely. The deterministic checks limit what it can do to the output.

## Spec exit check

| Requirement | Where |
|---|---|
| Three specialist Lambdas, each with its own focused prompt | `lambdas/src/{analyzer,scorer,rewriter}`, `common/prompts.py` |
| Step Functions chains analyze → score → rewrite with Retry/Catch | `infra/lib/constructs/pipeline.ts`, asserted in `infra/test/stack.test.ts` |
| All four Day-4 reliability patterns | [Reliability and security](#reliability-and-security) |
| Honesty guardrail (no fabricated experience, gaps listed) | [Honesty guardrail](#honesty-guardrail), `lambdas/tests/test_rewriter.py` |
| `cdk deploy` stands up the whole stack | [Deploy to AWS](#deploy-to-aws) |
| Claude via Bedrock `converse()`, no API key | `common/llm.py` |
| Submit → poll → draft + gap list render; email arrives | [Demo](#demo) |
| README with architecture diagram and deploy steps | this file |
| Code on GitHub | https://github.com/Chakravardhan-04/resume-tailor |
| Screenshot of a tailored draft + gap list | `docs/demo/screenshots/04-result.png` |
| Audit log from one real run (all three stages) | [`docs/demo/audit-log.json`](docs/demo/audit-log.json) |
