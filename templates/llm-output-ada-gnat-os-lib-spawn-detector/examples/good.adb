-- GOOD: no GNAT.OS_Lib.Spawn-family calls. The detector must NOT
-- flag any of these constructs.

with Ada.Text_IO;
with Ada.Directories;

procedure Good is
   Note : constant String := "see GNAT.OS_Lib.Spawn (Cmd, Args, OK) docs";
   --  Comment that mentions GNAT.OS_Lib.Spawn ( must not trigger.
   --  Even the fragment OS_Lib.Spawn ( inside this comment is masked.
begin
   --  Normal file ops via Ada.Directories — not spawn.
   Ada.Directories.Create_Directory ("build");

   --  String literal containing "GNAT.OS_Lib.Spawn (...)" as prose.
   Ada.Text_IO.Put_Line (Note);

   --  A variable named Spawn_Result is fine; we only flag .Spawn(
   --  preceded by an OS_Lib qualifier.
   declare
      Spawn_Result : Integer := 0;
   begin
      Spawn_Result := Spawn_Result + 1;
   end;

   --  Suppressed line: an audited spawn used in a build helper.
   GNAT.OS_Lib.Spawn ("./helpers/audited", Args.all, Success); -- spawn-ok
end Good;
