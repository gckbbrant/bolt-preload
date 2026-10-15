///|
/// Read selected measurement columns, converting explicitly to canonical units.
/// Calibration is (reading - force_zero) * force_gain, then the unit scale.
/// Other columns are ignored; every row must match the complete header width.
pub fn parse_load_csv(
  text : StringView,
  time_column? : String = "time_s",
  force_column? : String = "force_n",
  time_scale? : Double = 1.0,
  force_scale? : Double = 1.0,
  delimiter? : String = ",",
  skip_rows? : Int = 0,
  decimal_comma? : Bool = false,
  force_zero? : Double = 0.0,
  force_gain? : Double = 1.0,
) -> Result[Array[LoadSample], JointError] {
  if skip_rows < 0 {
    return Err(InvalidInput("skip_rows must be nonnegative"))
  }
  if time_column.trim().is_empty() ||
    force_column.trim().is_empty() ||
    time_column == force_column {
    return Err(
      InvalidInput("time and value columns must be nonempty and distinct"),
    )
  }
  if !finite(time_scale) ||
    time_scale <= 0.0 ||
    !finite(force_scale) ||
    force_scale <= 0.0 {
    return Err(InvalidInput("unit scales must be finite and positive"))
  }
  if !finite(force_zero) || !finite(force_gain) || force_gain == 0.0 {
    return Err(
      InvalidInput(
        "calibration zero must be finite; gain must be finite and nonzero",
      ),
    )
  }
  let samples : Array[LoadSample] = []
  let mut columns : (Int, Int)? = None
  let mut width = 0
  for index, raw in text.split("\n").collect() {
    if index < skip_rows {
      continue
    }
    let raw = raw.strip_suffix("\r").unwrap_or(raw)
    let line = raw.strip_prefix("\u{FEFF}").unwrap_or(raw)
    if line.trim().is_empty() {
      continue
    }
    let fields = match csv_fields(line, delimiter) {
      Ok(value) => value
      Err(error) =>
        return Err(InvalidInput("CSV line \{index + 1}: \{error.to_repr()}"))
    }
    if columns is None {
      columns = match measurement_columns(fields, time_column, force_column) {
        Ok(value) => Some(value)
        Err(error) => return Err(error)
      }
      width = fields.length()
      continue
    }
    if fields.length() != width {
      return Err(
        InvalidInput("CSV line \{index + 1}: expected \{width} columns"),
      )
    }
    let (time_index, value_index) = columns.unwrap()
    if decimal_comma &&
      (fields[time_index].contains(".") || fields[value_index].contains(".")) {
      return Err(
        InvalidInput(
          "CSV line \{index + 1}: decimal-comma input must not contain decimal dots or digit grouping",
        ),
      )
    }
    let time_text = if decimal_comma {
      fields[time_index].replace(old=",", new=".")
    } else {
      fields[time_index]
    }
    let value_text = if decimal_comma {
      fields[value_index].replace(old=",", new=".")
    } else {
      fields[value_index]
    }
    let time : Double = @string.from_str(time_text) catch {
      _ =>
        return Err(InvalidInput("CSV line \{index + 1}: invalid time number"))
    }
    let value : Double = @string.from_str(value_text) catch {
      _ =>
        return Err(InvalidInput("CSV line \{index + 1}: invalid force number"))
    }
    if !finite(time) || !finite(value) {
      return Err(InvalidInput("CSV line \{index + 1}: values must be finite"))
    }
    let shifted = value - force_zero
    let calibrated = if shifted == 0.0 { 0.0 } else { shifted * force_gain }
    if !finite(shifted) ||
      !finite(calibrated) ||
      (shifted != 0.0 && calibrated == 0.0) {
      return Err(
        InvalidInput(
          "CSV line \{index + 1}: sensor calibration cannot be represented",
        ),
      )
    }
    let sample : LoadSample = {
      time_s: time * time_scale,
      force_n: calibrated * force_scale,
    }
    if !finite(sample.time_s) ||
      !finite(sample.force_n) ||
      (time != 0.0 && sample.time_s == 0.0) ||
      (calibrated != 0.0 && sample.force_n == 0.0) {
      return Err(
        InvalidInput(
          "CSV line \{index + 1}: unit conversion cannot be represented",
        ),
      )
    }
    if sample.force_n < 0.0 {
      return Err(
        InvalidInput(
          "CSV line \{index + 1}: calibrated force must be nonnegative",
        ),
      )
    }
    if samples.last() is Some(previous) && sample.time_s <= previous.time_s {
      return Err(
        InvalidInput("CSV line \{index + 1}: timestamps must strictly increase"),
      )
    }
    samples.push(sample)
  }
  if samples.is_empty() {
    Err(InvalidInput("CSV has no force samples"))
  } else {
    Ok(samples)
  }
}

///|
/// Never serialize a separated prefix as a complete fatigue input.
pub fn stress_csv(history : HistoryResult) -> Result[String, JointError] {
  if history.separation is Some(event) {
    return Err(SeparationReached(event.force_n, event.separation_force_n))
  }
  if history.input_samples <= 0 ||
    history.samples.length() != history.input_samples {
    return Err(InvalidInput("stress export requires every input sample"))
  }
  if !finite(history.load_fraction) ||
    history.load_fraction <= 0.0 ||
    history.load_fraction >= 1.0 ||
    !finite(history.separation_force_n) ||
    history.separation_force_n <= 0.0 {
    return Err(InvalidInput("invalid history model parameters"))
  }
  for i, sample in history.samples {
    if !finite(sample.time_s) ||
      !finite(sample.stress_mpa) ||
      sample.stress_mpa <= 0.0 ||
      !finite(sample.clamp_force_n) ||
      sample.clamp_force_n <= 0.0 {
      return Err(InvalidInput("sample \{i}: invalid clamped stress sample"))
    }
    if i > 0 && sample.time_s <= history.samples[i - 1].time_s {
      return Err(InvalidInput("sample \{i}: timestamps must strictly increase"))
    }
  }
  let output = StringBuilder()
  output.write_string("time_s,stress_mpa\n")
  for sample in history.samples {
    output.write_string("\{sample.time_s},\{sample.stress_mpa}\n")
  }
  Ok(output.to_string())
}

///|
/// Serialize a complete, ordered history in canonical s and N units.
/// Reject empty histories, invalid numbers and non-increasing timestamps.
pub fn loads_csv(samples : ArrayView[LoadSample]) -> Result[String, JointError] {
  if samples.is_empty() {
    return Err(InvalidInput("CSV requires at least one sample"))
  }
  let output = StringBuilder()
  output.write_string("time_s,force_n\n")
  for i, sample in samples {
    if !finite(sample.time_s) || !finite(sample.force_n) || sample.force_n < 0.0 {
      return Err(InvalidInput("sample \{i}: invalid force or time"))
    }
    if i > 0 && sample.time_s <= samples[i - 1].time_s {
      return Err(InvalidInput("sample \{i}: timestamps must strictly increase"))
    }
    output.write_string("\{sample.time_s},\{sample.force_n}\n")
  }
  Ok(output.to_string())
}
