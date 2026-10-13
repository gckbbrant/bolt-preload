///|
/// Parse an unquoted two-column CSV; blank lines are ignored.
pub fn parse_load_csv(
  text : StringView,
) -> Result[Array[LoadSample], JointError] {
  let samples : Array[LoadSample] = []
  let mut header_seen = false
  for line_index, line in text.split("\n").collect() {
    let line = line.trim().strip_prefix("\u{FEFF}").unwrap_or(line.trim())
    if line.is_empty() {
      continue
    }
    if !header_seen {
      if line != "time_s,force_n" {
        return Err(InvalidInput("CSV header must be time_s,force_n"))
      }
      header_seen = true
      continue
    }
    let fields = line.split(",").collect()
    guard fields is [time, force] else {
      return Err(
        InvalidInput("CSV line \{line_index + 1}: expected two columns"),
      )
    }
    let sample : LoadSample = {
      time_s: @string.from_str(time.trim()),
      force_n: @string.from_str(force.trim()),
    } catch {
      _ =>
        return Err(InvalidInput("CSV line \{line_index + 1}: invalid number"))
    }
    if !finite(sample.time_s) || !finite(sample.force_n) || sample.force_n < 0.0 {
      return Err(
        InvalidInput(
          "CSV line \{line_index + 1}: nonfinite value or negative force",
        ),
      )
    }
    if samples.last() is Some(previous) && sample.time_s <= previous.time_s {
      return Err(
        InvalidInput(
          "CSV line \{line_index + 1}: timestamps must strictly increase",
        ),
      )
    }
    samples.push(sample)
  }
  if samples.is_empty() {
    Err(InvalidInput("CSV has no load samples"))
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
