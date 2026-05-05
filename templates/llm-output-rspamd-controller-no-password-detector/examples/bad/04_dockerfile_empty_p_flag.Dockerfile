FROM rspamd/rspamd:latest
EXPOSE 11334
CMD ["rspamd", "-f", "-u", "_rspamd", "-p", ""]
