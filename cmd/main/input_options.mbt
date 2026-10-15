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
