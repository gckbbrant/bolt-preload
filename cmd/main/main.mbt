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
  let history_options = measurement_options()
  history_options.append([
    @argparse.OptionArg(
      "stress",
      about="Write a complete time_s,stress_mpa CSV.",
    ),
    @argparse.OptionArg(
      "json",
      about="Write history JSON, including any separation event.",
    ),
    @argparse.OptionArg("svg", about="Write force distribution SVG."),
  ])
  let history = @argparse.Command(
    "history",
    about="Convert a load CSV to bolt stress before separation.",
    positionals=[
      @argparse.PositionArg("profile"),
      @argparse.PositionArg("loads"),
    ],
    options=history_options,
  )
  let command = @argparse.Command(
    "bolt-preload",
    about="Axial preloaded bolt joint calculations.",
    subcommands=[single, history, normalization_command()],
    subcommand_required=true,
  )
  let matches = command.parse()
  guard matches.subcommand is Some((name, args)) else {
    fail("expected analyze, history or normalize")
  }
  if name == "normalize" {
    normalize_input(args.values)
    return
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
  let outputs = [json_path, svg_path, stress_path].filter_map(fn(x) { x })
  prepare_outputs(inputs, outputs)
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
    let loads = read_measurements(required(args.values, "loads"), args.values)
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
