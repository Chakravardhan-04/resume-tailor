import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as authorizers from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { Stack } from 'aws-cdk-lib';
import { NAME_PREFIX } from '../config';
import { Auth } from './auth';
import { Construct } from 'constructs';
import { Functions } from './functions';

/**
 * HTTP API. Routes carry the /api prefix so CloudFront can forward /api/* unchanged,
 * which keeps the browser same-origin (no CORS needed).
 */
export class Api extends Construct {
  readonly httpApi: apigw.HttpApi;

  constructor(scope: Construct, id: string, props: { functions: Functions; auth: Auth }) {
    super(scope, id);

    this.httpApi = new apigw.HttpApi(this, 'HttpApi', {
      apiName: `${NAME_PREFIX}Api`,
      description: 'Resume tailoring: submit a job and poll its status',
    });

    // Every route requires a valid Cognito ID token (checked by API Gateway before any Lambda runs).
    const authorizer = new authorizers.HttpJwtAuthorizer(
      'JwtAuthorizer',
      `https://cognito-idp.${Stack.of(this).region}.amazonaws.com/${props.auth.userPool.userPoolId}`,
      { jwtAudience: [props.auth.client.userPoolClientId] },
    );

    const submitRoutes = this.httpApi.addRoutes({
      path: '/api/submit',
      methods: [apigw.HttpMethod.POST],
      integration: new integrations.HttpLambdaIntegration('SubmitIntegration', props.functions.submit),
      authorizer,
    });
    const statusRoutes = this.httpApi.addRoutes({
      path: '/api/jobs/{jobId}',
      methods: [apigw.HttpMethod.GET],
      integration: new integrations.HttpLambdaIntegration('StatusIntegration', props.functions.status),
      authorizer,
    });

    // Cost/abuse protection for an unauthenticated API: Bedrock calls are the expensive part.
    const stage = this.httpApi.defaultStage?.node.defaultChild as apigw.CfnStage;
    // Route-level settings must reference routes that already exist, so create the routes first.
    for (const route of [...submitRoutes, ...statusRoutes]) stage.node.addDependency(route);
    stage.defaultRouteSettings = { throttlingRateLimit: 10, throttlingBurstLimit: 20 };
    // routeSettings is an untyped map in L1, so keys must be PascalCase CloudFormation names.
    stage.routeSettings = {
      'POST /api/submit': { ThrottlingRateLimit: 1, ThrottlingBurstLimit: 3 },
    };
  }
}
