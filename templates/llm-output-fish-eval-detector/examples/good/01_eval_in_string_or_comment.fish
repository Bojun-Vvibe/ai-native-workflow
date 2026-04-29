# do not use eval here, it is dangerous
echo "the word eval should be safe in a string"
set msg "remember: eval $foo is bad"
echo $msg
