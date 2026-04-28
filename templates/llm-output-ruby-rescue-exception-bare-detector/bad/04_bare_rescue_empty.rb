def maybe_run(job)
  begin
    job.call
  rescue
  end
end
