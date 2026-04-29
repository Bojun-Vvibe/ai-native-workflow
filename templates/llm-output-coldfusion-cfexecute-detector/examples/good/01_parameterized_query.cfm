<cfquery name="q" datasource="ds">
    SELECT id, name FROM users WHERE id = <cfqueryparam value="#form.id#" cfsqltype="cf_sql_integer" />
</cfquery>
