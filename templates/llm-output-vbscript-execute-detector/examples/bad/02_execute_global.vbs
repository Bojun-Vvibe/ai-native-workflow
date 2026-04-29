' bad: ExecuteGlobal applied to a plug-in fragment loaded at runtime
Dim pluginText
pluginText = ReadAllText("plugins\hook.vbs")
ExecuteGlobal pluginText
