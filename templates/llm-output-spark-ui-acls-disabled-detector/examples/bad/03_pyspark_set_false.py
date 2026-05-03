from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("etl")
    .config("spark.acls.enable", "false")
    .config("spark.eventLog.enabled", "true")
    .getOrCreate()
)

df = spark.read.parquet("s3a://example/data/")
df.createOrReplaceTempView("events")
spark.sql("SELECT count(*) FROM events").show()
