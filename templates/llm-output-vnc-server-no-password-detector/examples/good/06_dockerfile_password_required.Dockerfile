FROM consol/ubuntu-xfce-vnc:latest
EXPOSE 5901
# VNC_PW must be supplied at runtime via secret, not hardcoded.
CMD ["/dockerstartup/startup.sh"]
