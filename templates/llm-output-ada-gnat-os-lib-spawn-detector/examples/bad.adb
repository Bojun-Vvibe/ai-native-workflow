-- BAD: every line below names a GNAT.OS_Lib.Spawn-family call. When
-- the program name or argument list is built from user input, this is
-- a direct command-injection sink.

with GNAT.OS_Lib;
with System.OS_Lib;

procedure Bad is
   Args    : GNAT.OS_Lib.Argument_List_Access;
   Success : Boolean;
   Pid     : GNAT.OS_Lib.Process_Id;
begin
   --  1. Fully-qualified blocking spawn.
   GNAT.OS_Lib.Spawn ("/bin/sh", Args.all, Success);

   --  2. Non-blocking variant with built argument list.
   Pid := GNAT.OS_Lib.Non_Blocking_Spawn ("rm", Args.all);

   --  3. Spawn_With_Filter — same risk surface.
   GNAT.OS_Lib.Spawn_With_Filter ("curl", Args.all, "filter.sh", Success);

   --  4. System.OS_Lib mirror — same library, different package path.
   System.OS_Lib.Spawn ("bash", Args.all, Success);

   --  5. `use`-shortened form (after `use GNAT.OS_Lib;` somewhere).
   OS_Lib.Spawn ("python3", Args.all, Success);

   --  6. Multi-line / odd-spacing form, also flagged.
   GNAT.OS_Lib.Spawn
     ("perl",
      Args.all,
      Success);
end Bad;
