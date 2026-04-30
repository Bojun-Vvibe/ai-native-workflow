"""Bad: tar.extract(member) with no filter= kwarg."""
import tarfile

def restore_one(path, dest, name):
    tf = tarfile.open(path)
    member = tf.getmember(name)
    tf.extract(member, dest)
