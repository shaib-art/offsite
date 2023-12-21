# Offsite

A tool for using a set of drives and storage locations to provide offside-backup
to a local set of drives and storage locations.

## Plan

### On-site
Run tool to read status from 'mailbox' (see line below) and collect local changes.  
The changes will be copied either directly or via 'mailbox' (e.g., Google Drive, a back-and-forth HDD, etc.)  
State of what went where will be kept locally, on the 'mailbox', and on the remotes.  

### Off-site
Run tool to identify changes in 'mailbox', detect the appropriate off-site locations to access,
and update each as they are made available - both by changes to their file systems,
and by changes to their state logs.
State will also be updated on the 'mailbox'.
