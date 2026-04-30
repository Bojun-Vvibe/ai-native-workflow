// mapReduce with a JS-as-string map function built from user input.
export async function mapReduceItems(coll, field) {
  return await coll.mapReduce("function() { emit(this[" + field + "], 1); }", "function(k,v){return Array.sum(v);}", { out: { inline: 1 } });
}
