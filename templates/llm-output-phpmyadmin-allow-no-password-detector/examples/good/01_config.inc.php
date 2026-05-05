<?php
/* Default-shaped phpMyAdmin config — empty-password login refused. */
$cfg['blowfish_secret'] = 'a8f5f167f44f4964e6c998dee827110c';
$i = 0;
$i++;
$cfg['Servers'][$i]['auth_type']       = 'cookie';
$cfg['Servers'][$i]['host']            = 'db';
$cfg['Servers'][$i]['AllowNoPassword'] = false;
$cfg['Servers'][$i]['compress']        = false;
