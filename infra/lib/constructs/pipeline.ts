import { Duration } from 'aws-cdk-lib';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import { Data } from './data';
import { Functions } from './functions';

export interface PipelineProps {
  data: Data;
  functions: Functions;
}

/**
 * analyzer -> scorer -> rewriter. The state object is the pipeline's memory:
 *   $.analysis (requirements)  $.match (score + gaps)  $.rewrite (result + pdf key)
 *
 * Retry: transient/throttling errors and Lambda service errors, with exponential backoff + jitter.
 * Catch: anything else records FAILED on the job (keeping any clearer message the stage already wrote).
 */
export class Pipeline extends Construct {
  readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: PipelineProps) {
    super(scope, id);
    const { data, functions } = props;

    const markFailed = new tasks.DynamoUpdateItem(this, 'MarkJobFailed', {
      table: data.table,
      key: {
        jobId: tasks.DynamoAttributeValue.fromString(sfn.JsonPath.stringAt('$.jobId')),
        sk: tasks.DynamoAttributeValue.fromString('META'),
      },
      updateExpression:
        'SET #st = :failed, errorCode = if_not_exists(errorCode, :code), ' +
        'errorMessage = if_not_exists(errorMessage, :msg), updatedAt = :now',
      expressionAttributeNames: { '#st': 'status' },
      expressionAttributeValues: {
        ':failed': tasks.DynamoAttributeValue.fromString('FAILED'),
        ':code': tasks.DynamoAttributeValue.fromString(sfn.JsonPath.stringAt('$.error.Error')),
        ':msg': tasks.DynamoAttributeValue.fromString('The pipeline could not complete. Please try again.'),
        ':now': tasks.DynamoAttributeValue.fromString(sfn.JsonPath.stringAt('$$.State.EnteredTime')),
      },
      resultPath: sfn.JsonPath.DISCARD,
    }).next(
      new sfn.Fail(this, 'PipelineFailed', {
        error: 'PipelineFailed',
        cause: 'A stage failed; see the job record and audit log.',
      }),
    );

    const stage = (id: string, fn: Functions['analyzer'], resultPath: string, timeout: number) => {
      const task = new tasks.LambdaInvoke(this, id, {
        lambdaFunction: fn,
        payloadResponseOnly: true,
        resultPath,
        taskTimeout: sfn.Timeout.duration(Duration.seconds(timeout)),
      });
      task.addRetry({
        errors: ['ThrottledError', 'ModelOutputError'],
        interval: Duration.seconds(5),
        maxAttempts: 3,
        backoffRate: 2,
        jitterStrategy: sfn.JitterType.FULL,
      });
      task.addRetry({
        errors: [
          'Lambda.ServiceException',
          'Lambda.AWSLambdaException',
          'Lambda.SdkClientException',
          'Lambda.TooManyRequestsException',
        ],
        interval: Duration.seconds(2),
        maxAttempts: 3,
        backoffRate: 2,
        jitterStrategy: sfn.JitterType.FULL,
      });
      task.addCatch(markFailed, { errors: ['States.ALL'], resultPath: '$.error' });
      return task;
    };

    const definition = stage('Analyze', functions.analyzer, '$.analysis', 130)
      .next(stage('Score', functions.scorer, '$.match', 130))
      .next(stage('Rewrite', functions.rewriter, '$.rewrite', 310));

    this.stateMachine = new sfn.StateMachine(this, 'StateMachine', {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: Duration.minutes(15),
      tracingEnabled: true,
      logs: {
        // ERROR only and no execution data: state carries resume evidence quotes (personal data).
        destination: new logs.LogGroup(this, 'StateMachineLogs', { retention: logs.RetentionDays.ONE_MONTH }),
        level: sfn.LogLevel.ERROR,
        includeExecutionData: false,
      },
    });

    // Submit needs the ARN; wire it here to avoid a Functions <-> Pipeline cycle.
    this.stateMachine.grantStartExecution(functions.submit);
    functions.submit.addEnvironment('STATE_MACHINE_ARN', this.stateMachine.stateMachineArn);
  }
}
