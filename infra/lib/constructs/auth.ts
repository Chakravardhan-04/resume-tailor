import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { Construct } from 'constructs';

/** Email + password sign-in. Self sign-up with an emailed verification code. */
export class Auth extends Construct {
  readonly userPool: cognito.UserPool;
  readonly client: cognito.UserPoolClient;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      selfSignUpEnabled: true,
      signInAliases: { email: true },
      signInCaseSensitive: false,
      autoVerify: { email: true },
      // The verified email is where results are sent, so it cannot be changed after sign-up.
      standardAttributes: { email: { required: true, mutable: false } },
      passwordPolicy: {
        minLength: 10,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      userVerification: {
        emailStyle: cognito.VerificationEmailStyle.CODE,
        emailSubject: 'Your Resume Tailor verification code',
        emailBody: 'Your verification code is {####}',
      },
      removalPolicy: RemovalPolicy.DESTROY, // demo stack; use RETAIN for real use
    });

    this.client = this.userPool.addClient('WebClient', {
      generateSecret: false, // browser app: public client
      // The app calls Cognito directly from the browser, so no hosted UI or callback URLs are needed.
      authFlows: { userPassword: true },
      preventUserExistenceErrors: true,
      enableTokenRevocation: true,
      idTokenValidity: Duration.hours(1),
      accessTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(30),
    });
  }
}
