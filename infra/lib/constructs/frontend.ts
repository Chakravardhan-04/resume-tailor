import * as fs from 'node:fs';
import { Duration, Fn, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';
import { Auth } from './auth';

export interface FrontendProps {
  httpApi: apigw.HttpApi;
  auth: Auth;
  /** Directory containing the built React app (frontend/dist). */
  distPath: string;
}

/** Private S3 bucket served through CloudFront (OAC). /api/* is forwarded to the HTTP API. */
export class Frontend extends Construct {
  readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: FrontendProps) {
    super(scope, id);

    if (!fs.existsSync(props.distPath)) {
      throw new Error(`Frontend build not found at ${props.distPath}. Run "npm ci && npm run build" in frontend/ first.`);
    }

    const siteBucket = new s3.Bucket(this, 'SiteBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const securityHeaders = new cloudfront.ResponseHeadersPolicy(this, 'SecurityHeaders', {
      securityHeadersBehavior: {
        contentSecurityPolicy: {
          override: true,
          contentSecurityPolicy:
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; " +
            `connect-src 'self' https://cognito-idp.${Stack.of(this).region}.amazonaws.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`,
        },
        strictTransportSecurity: {
          override: true,
          accessControlMaxAge: Duration.days(365),
          includeSubdomains: true,
        },
        contentTypeOptions: { override: true },
        frameOptions: { override: true, frameOption: cloudfront.HeadersFrameOption.DENY },
        referrerPolicy: { override: true, referrerPolicy: cloudfront.HeadersReferrerPolicy.NO_REFERRER },
      },
    });

    const apiHost = Fn.select(2, Fn.split('/', props.httpApi.apiEndpoint));

    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        responseHeadersPolicy: securityHeaders,
        compress: true,
      },
      additionalBehaviors: {
        '/api/*': {
          origin: new origins.HttpOrigin(apiHost, { protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY }),
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
          responseHeadersPolicy: securityHeaders,
        },
      },
      // No SPA error-page rewrite on purpose: it would also rewrite /api 404s into index.html.
    });

    new deploy.BucketDeployment(this, 'DeploySite', {
      sources: [
        deploy.Source.asset(props.distPath),
        // Runtime config read by the app at startup (public identifiers only, no secrets).
        deploy.Source.jsonData('config.json', {
          region: Stack.of(this).region,
          userPoolId: props.auth.userPool.userPoolId,
          clientId: props.auth.client.userPoolClientId,
        }),
      ],
      destinationBucket: siteBucket,
      distribution: this.distribution,
      distributionPaths: ['/*'],
    });
  }
}
