(*
  Block comment that mentions run script and do shell script.
  Should not produce any finding.
*)
tell application "Finder"
    set itemCount to count of items of desktop
end tell
