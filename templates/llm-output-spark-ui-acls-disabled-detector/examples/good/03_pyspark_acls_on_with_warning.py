from pyspark.sql import SparkSession

# Hardening note: do NOT do
#   .config("spark.acls.enable", "false")
# on a job that runs on shared infra; the driver UI on :4040 leaks
# query plans and lets anyone kill the job.
spark = (
    SparkSession.builder
    .appName("etl")
    .config("spark.acls.enable", "true")
    .config("spark.admin.acls", "ops-team")
    .config("spark.modify.acls", "etl-svc")
    .getOrCreate()
)

df = spark.read.parquet("s3a://example/data/")
df.show()
