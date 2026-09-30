import { Duration, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";
import * as ssm from "aws-cdk-lib/aws-ssm";
import type { Construct } from "constructs";
import { databaseName, type DeployConfig, describeDbInstance, parameterPrefix } from "./config.js";

export interface NovelData {
  vpc: ec2.IVpc;
  db: { instanceIdentifier: string; endpoint: string; port: number; securityGroupId: string; resourceId: string };
}

interface NovelDataStackProps extends StackProps {
  existing: DeployConfig["existing"];
}

// VPC・db・踏み台。構築ごとの設定(SSM の /novel/deploy/config)に既存のものの ID があれば参照し、無ければ作る。
// 作るときも費用を抑える形にする(NAT の無い VPC、db.t4g.micro の RDS、t4g.nano の踏み台と EC2 Instance Connect Endpoint)。
// 手元の道具(tool.aws.rds)とほかのスタックが引く値は、SSM パラメータ /novel/* に置く
export class NovelDataStack extends Stack {
  readonly data: NovelData;

  constructor(scope: Construct, id: string, props: NovelDataStackProps) {
    super(scope, id, props);
    const { existing } = props;

    const existingDb = existing.dbInstanceIdentifier ? describeDbInstance(existing.dbInstanceIdentifier) : undefined;
    const vpcId = existing.vpcId ?? existingDb?.vpcId;
    const vpc = vpcId
      ? ec2.Vpc.fromLookup(this, "Vpc", { vpcId })
      : new ec2.Vpc(this, "Vpc", {
        maxAzs: 2,
        natGateways: 0,
        subnetConfiguration: [{ name: "isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 }],
      });

    let db: NovelData["db"];
    let masterSecretArn: string;
    if (existing.dbInstanceIdentifier && existingDb) {
      db = { instanceIdentifier: existing.dbInstanceIdentifier, ...existingDb };
      masterSecretArn = existingDb.masterSecretArn;
    } else {
      const dbSecurityGroup = new ec2.SecurityGroup(this, "DbSecurityGroup", { vpc, allowAllOutbound: false });
      const instance = new rds.DatabaseInstance(this, "Db", {
        engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_18_3 }),
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
        allocatedStorage: 20,
        vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
        securityGroups: [dbSecurityGroup],
        publiclyAccessible: false,
        credentials: rds.Credentials.fromGeneratedSecret("postgres"),
        iamAuthentication: true,
        backupRetention: Duration.days(7),
        deletionProtection: true,
        removalPolicy: RemovalPolicy.SNAPSHOT,
      });
      db = {
        instanceIdentifier: instance.instanceIdentifier,
        endpoint: instance.dbInstanceEndpointAddress,
        port: 5432,
        securityGroupId: dbSecurityGroup.securityGroupId,
        resourceId: instance.instanceResourceId!,
      };
      masterSecretArn = instance.secret!.secretArn;
    }

    const bastion = existing.bastion ?? this.createBastion(vpc, db);

    const parameters: Record<string, string> = {
      "db/instance-identifier": db.instanceIdentifier,
      "db/endpoint": db.endpoint,
      "db/port": String(db.port),
      "db/name": databaseName,
      "db/master-secret-arn": masterSecretArn,
      "bastion/instance-id": bastion.instanceId,
      "bastion/instance-connect-endpoint-id": bastion.instanceConnectEndpointId,
    };
    for (const [name, value] of Object.entries(parameters)) {
      new ssm.StringParameter(this, name, {
        parameterName: `${parameterPrefix}/${name}`,
        stringValue: value,
      });
    }

    this.data = { vpc, db };
  }

  // 公開 IP の無い踏み台へは、EC2 Instance Connect Endpoint 越しに ssh する(料金は掛からない)
  private createBastion(vpc: ec2.IVpc, db: NovelData["db"]) {
    const endpointSecurityGroup = new ec2.SecurityGroup(this, "InstanceConnectEndpointSecurityGroup", {
      vpc,
      allowAllOutbound: false,
    });
    const bastionSecurityGroup = new ec2.SecurityGroup(this, "BastionSecurityGroup", { vpc, allowAllOutbound: true });
    bastionSecurityGroup.addIngressRule(endpointSecurityGroup, ec2.Port.tcp(22));
    endpointSecurityGroup.addEgressRule(bastionSecurityGroup, ec2.Port.tcp(22));
    ec2.SecurityGroup.fromSecurityGroupId(this, "BastionDbSecurityGroup", db.securityGroupId, { mutable: true })
      .addIngressRule(bastionSecurityGroup, ec2.Port.tcp(db.port), "bastion");

    const subnet = vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_ISOLATED }).subnets[0];
    const instance = new ec2.Instance(this, "Bastion", {
      vpc,
      vpcSubnets: { subnets: [subnet] },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.NANO),
      machineImage: ec2.MachineImage.latestAmazonLinux2023({ cpuType: ec2.AmazonLinuxCpuType.ARM_64 }),
      securityGroup: bastionSecurityGroup,
    });
    const endpoint = new ec2.CfnInstanceConnectEndpoint(this, "InstanceConnectEndpoint", {
      subnetId: subnet.subnetId,
      securityGroupIds: [endpointSecurityGroup.securityGroupId],
    });
    return { instanceId: instance.instanceId, instanceConnectEndpointId: endpoint.attrId };
  }
}
