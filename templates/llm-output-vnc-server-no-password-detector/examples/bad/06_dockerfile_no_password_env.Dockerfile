FROM consol/ubuntu-xfce-vnc:latest
EXPOSE 5901
ENV VNC_NO_PASSWORD=1
CMD ["/dockerstartup/startup.sh"]
