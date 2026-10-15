///|
struct InputFormat {
  time_column : String
  force_column : String
  time_unit : String
  force_unit : String
  delimiter : String
  skip_rows : Int
  decimal_separator : String
  force_zero : Double
  force_gain : Double
} derive(ToJson)

///|
fn InputFormat::options(self : InputFormat) -> Map[String, Array[String]] {
  {
    "time-column": [self.time_column],
    "force-column": [self.force_column],
    "time-unit": [self.time_unit],
    "force-unit": [self.force_unit],
    "delimiter": [self.delimiter],
    "skip-rows": [self.skip_rows.to_string()],
    "decimal-separator": [self.decimal_separator],
    "force-zero": [self.force_zero.to_string()],
    "force-gain": [self.force_gain.to_string()],
  }
}

///|
fn format_from_values(values : Map[String, Array[String]]) -> InputFormat raise {
  let time_column = optional(values, "time-column").unwrap_or("time_s")
  let value_column = optional(values, "force-column").unwrap_or("force_n")
  if time_column.trim().is_empty() ||
    value_column.trim().is_empty() ||
    time_column == value_column {
    fail("time and value columns must be nonempty and distinct")
  }
  ignore(input_time_scale(values))
  ignore(input_force_scale(values))
  ignore(input_delimiter(values))
  let skip_rows = input_skip_rows(values)
  ignore(input_decimal_comma(values))
  let zero = calibration_number(values, "force-zero", 0.0)
  let gain = calibration_number(values, "force-gain", 1.0)
  if zero.is_nan() ||
    zero.is_inf() ||
    gain.is_nan() ||
    gain.is_inf() ||
    gain == 0.0 {
    fail("calibration zero must be finite; gain must be finite and nonzero")
  }
  {
    time_column,
    force_column: value_column,
    time_unit: optional(values, "time-unit").unwrap_or("s"),
    force_unit: optional(values, "force-unit").unwrap_or("N"),
    delimiter: optional(values, "delimiter").unwrap_or("comma"),
    skip_rows,
    decimal_separator: optional(values, "decimal-separator").unwrap_or("dot"),
    force_zero: zero,
    force_gain: gain,
  }
}
