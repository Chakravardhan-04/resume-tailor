import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { Construct } from 'constructs';
import { Functions } from './functions';

/**
 * HTTP API. Routes carry the /api prefix so CloudFront can forward /api/* unchanged,
 * which keeps the browser same-origin (no CORS needed).
 */
export class Api extends Construct {
  readonly httpApi: apigw.HttpApi;

  constructor(scope: Construct, id: string, props: { functions: Functions }) {
    super(scope, id);

    this.httpApi = new apigw.HttpApi(this, 'HttpApi', {
      description: 'Resume tailoring: submit a job and poll its status',
    });

    this.httpApi.addRoutes({
      path: '/api/submit',
      methods: [apigw.HttpMethod.POST],
      integration: new integrations.HttpLambdaIntegration('SubmitIntegration', props.functions.submit),
    });
    this.httpApi.addRoutes({
      path: '/api/jobs/{jobId}',
      methods: [apigw.HttpMethod.GET],
      integration: new integrations.HttpLambdaIntegration('StatusIntegration', props.functions.status),
    });

    // Cost/abuse protection for an unauthenticated API: Bedrock calls are the expensive part.
    const stage = this.httpApi.defaultStage?.node.defaultChild as apigw.CfnStage;
    stage.defaultRouteSettings = { throttlingRateLimit: 10, throttlingBurstLimit: 20 };
    // routeSettings is an untyped map in L1, so keys must be PascalCase CloudFormation names.
    stage.routeSettings = {
      'POST /api/submit': { ThrottlingRateLimit: 1, ThrottlingBurstLimit: 3 },
    };
  }
}
