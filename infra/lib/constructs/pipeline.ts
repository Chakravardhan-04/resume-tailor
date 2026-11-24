import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { NAME_PREFIX } from '../config';
import { Data } from './data';
import { Functions } from './functions';

/**
 * The Step Functions state machine:  Analyze -> Score -> Rewrite
 *
 * The state object is the pipeline's memory. It starts as {jobId, inputs} and each stage adds its output:
 *   $.analysis (requirements)   $.match (score, matched, gaps)   $.rewrite (result, PDF key, email status)
 */
export class Pipeline extends Construct {
  readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: { data: Data; functions: Functions }) {
    super(scope, id);
    const { data, functions } = props;

    // Catch target: mark the job FAILED, keeping the clearer message the stage may have written, then fail.
    const markFailed = new tasks.DynamoUpdateItem(this, 'MarkJobFailed', {
      table: data.table,
      key: {
        jobId: tasks.DynamoAttributeValue.fromString(sfn.JsonPath.stringAt('$.jobId')),
        sk: tasks.DynamoAttributeValue.fromString('META'),
      },
      updateExpression: 'SET #st = :failed, errorCode = if_not_exists(errorCode, :code), errorMessage = if_not_exists(errorMessage, :msg)',
      expressionAttributeNames: { '#st': 'status' },
      expressionAttributeValues: {
        ':failed': tasks.DynamoAttributeValue.fromString('FAILED'),
        ':code': tasks.DynamoAttributeValue.fromString(sfn.JsonPath.stringAt('$.error.Error')),
        ':msg': tasks.DynamoAttributeValue.fromString('The pipeline could not complete. Please try again.'),
      },
      resultPath: sfn.JsonPath.DISCARD,
    }).next(new sfn.Fail(this, 'PipelineFailed'));

    const stage = (name: string, fn: lambda.IFunction, resultPath: string) => {
      const task = new tasks.LambdaInvoke(this, name, { lambdaFunction: fn, payloadResponseOnly: true, resultPath });
      // Retry: temporary problems (Bedrock busy, agent hit its turn limit, Lambda hiccups), with backoff + jitter.
      task.addRetry({
        errors: ['ThrottledError', 'ModelOutputError', 'Lambda.ServiceException', 'Lambda.TooManyRequestsException'],
        interval: Duration.seconds(5),
        maxAttempts: 3,
        backoffRate: 2,
        jitterStrategy: sfn.JitterType.FULL,
      });
      // Catch: anything else (e.g. InputError for a missing document) goes straight to MarkJobFailed.
      task.addCatch(markFailed, { errors: ['States.ALL'], resultPath: '$.error' });
      return task;
    };

    const definition = stage('Analyze', functions.analyzer, '$.analysis')
      .next(stage('Score', functions.scorer, '$.match'))
      .next(stage('Rewrite', functions.rewriter, '$.rewrite'));

    this.stateMachine = new sfn.StateMachine(this, 'StateMachine', {
      stateMachineName: `${NAME_PREFIX}Pipeline`,
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: Duration.minutes(15),
      logs: {
        destination: new logs.LogGroup(this, 'StateMachineLogs', {
          logGroupName: `/aws/vendedlogs/states/${NAME_PREFIX}Pipeline`,
          retention: logs.RetentionDays.ONE_MONTH,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
        level: sfn.LogLevel.ERROR,
        includeExecutionData: false, // the state contains resume text: keep it out of the logs
      },
    });

    // The submit Lambda starts executions.
    this.stateMachine.grantStartExecution(functions.submit);
    functions.submit.addEnvironment('STATE_MACHINE_ARN', this.stateMachine.stateMachineArn);
  }
}
