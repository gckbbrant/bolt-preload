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
