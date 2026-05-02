# zkCli.sh transcript with a real digest ACL
addauth digest deployer:s3cret-from-vault
create /app "init"
setAcl /app digest:deployer:Hk3VHrI4Lkk9o5fYf0E1Y5wD6Ms=:cdrwa
