import { homeSearch, serviceSearch } from "./search";

test("a missing tab reads as the default", () => {
  // A bare `/` is Home's board. Were the tab required, every link
  // written by hand would have to name it.
  expect(homeSearch({})).toMatchObject({ tab: "board" });
});

test("an unknown tab falls back rather than rendering nothing", () => {
  // A stale bookmark or a typo must not leave a blank screen.
  expect(homeSearch({ tab: "nonsense" })).toMatchObject({ tab: "board" });
});

test("severity is parsed to a number the API accepts", () => {
  // The parameter reaches the API as `status__severity`, an integer.
  // A string would be a 400 from a control the reader just used.
  expect(homeSearch({ tab: "board", severity: "2" })).toMatchObject({
    severity: 2,
  });
});

test("a severity outside the six values is dropped", () => {
  // Severity is 0 to 5. Nothing else is a state the API knows.
  expect(homeSearch({ severity: "9" }).severity).toBeUndefined();
});

test("the service screen keeps its own three tabs", () => {
  // Each screen validates only the tabs it has, so a link from one
  // screen cannot select a tab another screen owns.
  expect(serviceSearch({ tab: "timeline" })).toMatchObject({
    tab: "components",
  });
});
