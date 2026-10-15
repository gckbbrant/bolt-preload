///|
struct InputSummary {
  input_samples : Int
  time_start_s : Double
  time_end_s : Double
  minimum_force_n : Double
  maximum_force_n : Double
} derive(ToJson)

///|
async fn read_measurements(
  path : String,
  values : Map[String, Array[String]],
) -> Array[@app.LoadSample] {
  match
    @app.parse_load_csv(
      @fs.read_file(path).text(),
      time_column=optional(values, "time-column").unwrap_or("time_s"),
      force_column=optional(values, "force-column").unwrap_or("force_n"),
      time_scale=input_time_scale(values),
      force_scale=input_force_scale(values),
      delimiter=input_delimiter(values),
      skip_rows=input_skip_rows(values),
      decimal_comma=input_decimal_comma(values),
    ) {
    Ok(value) => value
    Err(error) => fail(@json.to_json(error).stringify())
  }
}

///|
fn normalization_command() -> @argparse.Command {
  let options = measurement_options()
  options.push(OptionArg("csv", about="Write canonical time_s,force_n CSV."))
  options.push(
    OptionArg(
      "json",
      about="Write sample count, time endpoints and force range JSON.",
    ),
  )
  Command(
    "normalize",
    about="Check measurement input and convert to s and N without model calculations.",
    positionals=[PositionArg("input")],
    options~,
  )
}

///|
async fn normalize_input(values : Map[String, Array[String]]) -> Unit {
  let input = required(values, "input")
  let csv_path = optional(values, "csv")
  let json_path = optional(values, "json")
  prepare_outputs([input], [csv_path, json_path].filter_map(fn(x) { x }))
  let samples = read_measurements(input, values)
  let csv = match @app.loads_csv(samples) {
    Ok(value) => value
    Err(error) => fail(@json.to_json(error).stringify())
  }
  let mut minimum = samples[0].force_n
  let mut maximum = minimum
  for sample in samples {
    minimum = minimum.min(sample.force_n)
    maximum = maximum.max(sample.force_n)
  }
  let summary : InputSummary = {
    input_samples: samples.length(),
    time_start_s: samples[0].time_s,
    time_end_s: samples[samples.length() - 1].time_s,
    minimum_force_n: minimum,
    maximum_force_n: maximum,
  }
  if csv_path is Some(path) {
    @fs.write_file(path, csv, create_mode=CreateOrTruncate)
  }
  if json_path is Some(path) {
    @fs.write_file(
      path,
      @json.to_json(summary).stringify(indent=2) + "\n",
      create_mode=CreateOrTruncate,
    )
  }
  @stdio.stdout.write(
    "Samples: \{summary.input_samples}; time: \{summary.time_start_s}..\{summary.time_end_s} s; force: \{minimum}..\{maximum} N\n",
  )
}
