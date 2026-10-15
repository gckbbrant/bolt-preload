///|
fn input_time_scale(values : Map[String, Array[String]]) -> Double raise {
  match optional(values, "time-unit") {
    None | Some("s") => 1.0
    Some("ms") => 0.001
    _ => fail("time-unit must be s or ms")
  }
}

///|
fn input_delimiter(values : Map[String, Array[String]]) -> String raise {
  match optional(values, "delimiter") {
    None | Some("comma") => ","
    Some("semicolon") => ";"
    Some("tab") => "\t"
    _ => fail("delimiter must be comma, semicolon or tab")
  }
}

///|
fn input_force_scale(values : Map[String, Array[String]]) -> Double raise {
  match optional(values, "force-unit") {
    None | Some("N") => 1.0
    Some("kN") => 1000.0
    _ => fail("force-unit must be N or kN")
  }
}

///|
fn input_skip_rows(values : Map[String, Array[String]]) -> Int raise {
  let rows : Int = match optional(values, "skip-rows") {
    None => 0
    Some(text) => @string.from_str(text)
  }
  if rows < 0 {
    fail("skip-rows must be nonnegative")
  }
  rows
}

///|
fn input_decimal_comma(values : Map[String, Array[String]]) -> Bool raise {
  match optional(values, "decimal-separator") {
    None | Some("dot") => false
    Some("comma") => true
    _ => fail("decimal-separator must be dot or comma")
  }
}

///|
fn measurement_options() -> Array[@argparse.OptionArg] {
  [
    OptionArg(
      "input-config",
      about="Flat versioned measurement preset JSON; explicit options override it.",
    ),
    OptionArg("time-column", about="Time column name; default time_s."),
    OptionArg("force-column", about="Force column name; default force_n."),
    OptionArg("time-unit", about="Input time unit: s or ms; default s."),
    OptionArg("force-unit", about="Input force unit: N or kN; default N."),
    OptionArg(
      "force-zero",
      about="Raw channel reading at zero force; default 0.",
      allow_hyphen_values=true,
    ),
    OptionArg(
      "force-gain",
      about="Declared input force unit per raw reading, finite and nonzero; default 1.",
      allow_hyphen_values=true,
    ),
    OptionArg("delimiter", about="CSV separator: comma, semicolon or tab."),
    OptionArg(
      "skip-rows",
      about="Physical preamble lines before header; default 0.",
    ),
    OptionArg(
      "decimal-separator",
      about="Input decimal separator: dot or comma; default dot.",
    ),
  ]
}

///|
fn calibration_number(
  values : Map[String, Array[String]],
  key : String,
  fallback : Double,
) -> Double raise {
  match optional(values, key) {
    None => fallback
    Some(text) =>
      @string.from_str(text) catch {
        _ => fail("\{key} must be a number")
      }
  }
}
