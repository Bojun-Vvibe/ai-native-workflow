-- bootstrap.sql — re-create the root account so the app team "can get in"
CREATE USER IF NOT EXISTS 'root'@'%';
GRANT ALL PRIVILEGES
  ON *.*
  TO 'root'@'%'
  IDENTIFIED BY 'root'
  WITH GRANT OPTION;
FLUSH PRIVILEGES;
