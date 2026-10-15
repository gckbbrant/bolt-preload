///|
extern "C" fn exit_process(code : Int) -> Unit = "exit"

///|
fn required(values : Map[String, Array[String]], key : String) -> String raise {
  match values.get(key) {
    Some([value]) => value
    _ => fail("expected one value for \{key}")
  }
}

///|
fn optional(values : Map[String, Array[String]], key : String) -> String? raise {
  match values.get(key) {
    Some([value]) => Some(value)
    None => None
    _ => fail("expected one value for \{key}")
  }
}

///|
async fn output_identity(path : String) -> String {
  if @fs.exists(path) {
    return @fs.realpath(path).replace(old="\\", new="/").to_lower()
  }
  let parts = path.replace(old="\\", new="/").split("/").collect()
  let name = parts[parts.length() - 1]
  if name.is_empty() {
    fail("output must name a file")
  }
  let parent = if parts.length() == 1 {
    "."
  } else {
    parts[:parts.length() - 1].join("/")
  }
  (@fs.realpath(parent).replace(old="\\", new="/") + "/" + name.to_owned()).to_lower()
}

///|
async fn run() -> Unit {
  let single = @argparse.Command(
    "analyze",
    about="Analyze one axial tensile force.",
    positionals=[@argparse.PositionArg("profile")],
    options=[
      @argparse.OptionArg(
        "force",
        required=true,
        about="External tensile force in N.",
      ),
      @argparse.OptionArg("json", about="Write result JSON."),
      @argparse.OptionArg("svg", about="Write force distribution SVG."),
    ],
  )
  let history = @argparse.Command(
    "history",
    about="Convert a load CSV to bolt stress before separation.",
    positionals=[
      @argparse.PositionArg("profile"),
      @argparse.PositionArg("loads"),
    ],
    options=[
      @argparse.OptionArg(
        "stress",
        about="Write a complete time_s,stress_mpa CSV.",
      ),
      @argparse.OptionArg(
        "json",
        about="Write history JSON, including any separation event.",
      ),
      @argparse.OptionArg("svg", about="Write force distribution SVG."),
      @argparse.OptionArg(
        "time-column",
        about="Time column name; default time_s.",
      ),
      @argparse.OptionArg(
        "force-column",
        about="Force column name; default force_n.",
      ),
      @argparse.OptionArg(
        "time-unit",
        about="Input time unit: s or ms; default s.",
      ),
      @argparse.OptionArg(
        "force-unit",
        about="Input force unit: N or kN; default N.",
      ),
      @argparse.OptionArg(
        "delimiter",
        about="CSV separator: comma, semicolon or tab.",
      ),
    ],
  )
  let command = @argparse.Command(
    "bolt-preload",
    about="Axial preloaded bolt joint calculations.",
    subcommands=[single, history],
    subcommand_required=true,
  )
  let matches = command.parse()
  guard matches.subcommand is Some((name, args)) else {
    fail("expected analyze or history")
  }
  let profile_path = required(args.values, "profile")
  let loads_path = optional(args.values, "loads")
  let json_path = optional(args.values, "json")
  let svg_path = optional(args.values, "svg")
  let stress_path = optional(args.values, "stress")
  let inputs = [profile_path]
  if loads_path is Some(path) {
    inputs.push(path)
  }
  let input_ids : Array[String] = []
  for path in inputs {
    input_ids.push(@fs.realpath(path).replace(old="\\", new="/").to_lower())
  }
  let outputs = [json_path, svg_path, stress_path].filter_map(fn(x) { x })
  let output_ids : Array[String] = []
  for path in outputs {
    let id = output_identity(path)
    if input_ids.contains(id) {
      fail("output must not overwrite an input: \{path}")
    }
    if output_ids.contains(id) {
      fail("output paths must be distinct")
    }
    output_ids.push(id)
  }
  // Clear old exports so failed analysis cannot leave stale fatigue data.
  for path in outputs {
    if @fs.exists(path) {
      @fs.remove(path)
    }
  }
  let profile : @app.JointProfile = @json.from_json(
    @json.parse(@fs.read_file(profile_path).text()),
  )
  let mut separated = false
  if name == "analyze" {
    let force : Double = @string.from_str(required(args.values, "force"))
    let result = match @app.analyze_joint(profile, force) {
      Ok(value) => value
      Err(error) => fail(@json.to_json(error).stringify())
    }
    @stdio.stdout.write(
      "Bolt: \{result.bolt_force_n} N; clamp: \{result.clamp_force_n} N; stress: \{result.stress_mpa} MPa; separation: \{result.separation_force_n} N\n",
    )
    if json_path is Some(path) {
      @fs.write_file(
        path,
        @json.to_json(result).stringify(indent=2) + "\n",
        create_mode=@fs.CreateOrTruncate,
      )
    }
  } else {
    let loads = match
      @app.parse_load_csv(
        @fs.read_file(required(args.values, "loads")).text(),
        time_column=optional(args.values, "time-column").unwrap_or("time_s"),
        force_column=optional(args.values, "force-column").unwrap_or("force_n"),
        time_scale=input_time_scale(args.values),
        force_scale=input_force_scale(args.values),
        delimiter=input_delimiter(args.values),
      ) {
      Ok(value) => value
      Err(error) => fail(@json.to_json(error).stringify())
    }
    let result = match @app.analyze_load_history(profile, loads) {
      Ok(value) => value
      Err(error) => fail(@json.to_json(error).stringify())
    }
    if json_path is Some(path) {
      @fs.write_file(
        path,
        @json.to_json(result).stringify(indent=2) + "\n",
        create_mode=@fs.CreateOrTruncate,
      )
    }
    match result.separation {
      Some(event) => {
        separated = true
        @stdio.stderr.write(
          "Separation at sample \{event.sample_index}, t=\{event.time_s} s, F=\{event.force_n} N (limit \{event.separation_force_n} N). Stress CSV not exported.\n",
        )
      }
      None => {
        let csv = match @app.stress_csv(result) {
          Ok(value) => value
          Err(_) => fail("history cannot be exported")
        }
        if stress_path is Some(path) {
          @fs.write_file(path, csv, create_mode=@fs.CreateOrTruncate)
        }
        @stdio.stdout.write(
          "Converted \{result.samples.length()} samples; C=\{result.load_fraction}; separation=\{result.separation_force_n} N\n",
        )
      }
    }
  }
  if svg_path is Some(path) {
    let svg = match @app.render_svg(profile) {
      Ok(value) => value
      Err(error) => fail(@json.to_json(error).stringify())
    }
    @fs.write_file(path, svg, create_mode=@fs.CreateOrTruncate)
  }
  if separated {
    exit_process(1)
  }
}

///|
async fn main {
  run() catch {
    error => {
      @stdio.stderr.write("bolt-preload: \{error}\n")
      exit_process(2)
    }
  }
}
