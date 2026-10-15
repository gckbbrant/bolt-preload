///|
test "CSV handles BOM and CRLF; ambiguous or invalid rows are rejected" {
  let loads = @app.parse_load_csv("\u{FEFF}time_s,force_n\r\n0,0\r\n1,5000\r\n").unwrap()
  assert_eq(loads.length(), 2)
  assert_eq(loads[1].force_n, 5000.0)
  assert_true(@app.parse_load_csv("time_s,force_n\n0,1\n0,2") is Err(_))
  assert_true(@app.parse_load_csv("time_s,force_n\n0,nan") is Err(_))
  assert_true(@app.parse_load_csv("time_s,force_n\n0,-1") is Err(_))
  assert_true(@app.parse_load_csv("time_s,force_n\n0,1,2") is Err(_))
  assert_true(@app.parse_load_csv("time_s,force_n") is Err(_))
}

///|
test "stress export rejects partial histories" {
  let p : @app.JointProfile = {
    bolt_stiffness_n_per_mm: 200000.0,
    joint_stiffness_n_per_mm: 800000.0,
    preload_n: 10000.0,
    stress_area_mm2: 50.0,
  }
  let valid = @app.analyze_load_history(p, [
    { time_s: 0.0, force_n: 0.0, },
    { time_s: 1.0, force_n: 5000.0, },
  ]).unwrap()
  assert_eq(
    @app.stress_csv(valid).unwrap(),
    "time_s,stress_mpa\n0,200\n1,220\n",
  )
  let separated = @app.analyze_load_history(p, [
    { time_s: 0.0, force_n: 0.0, },
    { time_s: 1.0, force_n: 12500.0, },
  ]).unwrap()
  assert_true(@app.stress_csv(separated) is Err(_))
}

///|
test "publicly constructed history cannot disguise a partial export" {
  let p : @app.JointProfile = {
    bolt_stiffness_n_per_mm: 200000.0,
    joint_stiffness_n_per_mm: 800000.0,
    preload_n: 10000.0,
    stress_area_mm2: 50.0,
  }
  let valid = @app.analyze_load_history(p, [
    { time_s: 0.0, force_n: 0.0, },
    { time_s: 1.0, force_n: 5000.0, },
  ]).unwrap()
  let partial = { ..valid, samples: valid.samples[:1].to_owned(), }
  assert_true(@app.stress_csv(partial) is Err(@app.InvalidInput(_)))
}

///|
test "measurement columns, quoted notes and explicit unit scales" {
  let samples = @app.parse_load_csv(
    "\u{FEFF}note;Load;Clock\r\n\"sensor; A\"\"x\"\"\";0;0\r\n\"sensor B\";5;1000\r\n\"sensor C\";2;2000\r\n",
    time_column="Clock",
    force_column="Load",
    time_scale=0.001,
    force_scale=1000.0,
    delimiter=";",
  ).unwrap()
  assert_eq(samples.length(), 3)
  assert_eq(samples[1].time_s, 1.0)
  assert_eq(samples[1].force_n, 5000.0)
  let tabbed = @app.parse_load_csv(
    "Clock\tLoad\tnote\n0\t1\t\n1\t2\t\n",
    time_column="Clock",
    force_column="Load",
    delimiter="\t",
  ).unwrap()
  assert_eq(tabbed.length(), 2)
}

///|
test "measurement imports reject ambiguous columns and lossy conversion" {
  for
    text in [
      "time_s,force_n,force_n\n0,1,2", "time_s,other\n0,1", "time_s,force_n,note\n0,1",
      "time_s,force_n\n0,\"1", "time_s,force_n\n0,\"1\"oops",
    ] {
    assert_true(@app.parse_load_csv(text) is Err(_))
  }
  assert_true(
    @app.parse_load_csv("time_s,force_n\n0,1e308", force_scale=1000.0) is Err(_),
  )
  assert_true(
    @app.parse_load_csv("time_s,force_n\n0,1e-300", force_scale=1.0e-100)
    is Err(_),
  )
  assert_true(
    @app.parse_load_csv("time_s,force_n\n0,1", time_scale=0.0) is Err(_),
  )
  assert_true(
    @app.parse_load_csv("time_s,force_n\n0,1", force_column="time_s") is Err(_),
  )
}

///|
test "explicit preamble skipping and decimal comma keep original line numbers" {
  let result = @app.parse_load_csv(
    "Instrument export\nsep=;\nClock;Value\n0,0;0,0\n1000,5;1,25\n",
    time_column="Clock",
    force_column="Value",
    delimiter=";",
    time_scale=0.001,
    skip_rows=2,
    decimal_comma=true,
  ).unwrap()
  assert_eq(result.length(), 2)
  assert_true(result[1].time_s.is_close(1.0005))
  assert_eq(result[1].force_n, 1.25)
  assert_true(
    @app.parse_load_csv("time_s,force_n\n0,1", skip_rows=-1) is Err(_),
  )
  assert_true(@app.parse_load_csv("time_s,force_n\n0,1", skip_rows=9) is Err(_))
}

///|
test "decimal comma never guesses mixed decimal or grouping formats" {
  for value in ["1.25", "1.234,5", "1,234,5"] {
    assert_true(
      @app.parse_load_csv(
        "time_s;force_n\n0;" + value,
        delimiter=";",
        decimal_comma=true,
      )
      is Err(_),
    )
  }
  let broken = @app.parse_load_csv(
    "metadata\nmetadata\ntime_s;force_n\n0;bad",
    delimiter=";",
    skip_rows=2,
    decimal_comma=true,
  )
  assert_true(
    broken is Err(@app.InvalidInput(message)) && message.contains("line 4"),
  )
}
