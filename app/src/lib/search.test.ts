import {
  boardSearch,
  componentUpdatesSearch,
  discoverSearch,
  serviceComponentsSearch,
  updatesSearch,
} from "./search";

// A tab is a path now, so a schema carries filters only. Each screen
// validates the filters its own tab takes, and nothing else.

test("severity is parsed to a number the API accepts", () => {
  // The parameter reaches the API as `status__severity`, an integer.
  // A string would be a 400 from a control the reader just used.
  expect(boardSearch({ severity: "2" })).toMatchObject({ severity: 2 });
});

test("a severity outside the six values is dropped", () => {
  // Severity is 0 to 5. Nothing else is a state the API knows.
  expect(boardSearch({ severity: "9" }).severity).toBeUndefined();
});

test("severity zero survives, because it is the worst one", () => {
  // A falsy check would drop a major outage and show everything.
  expect(boardSearch({ severity: "0" })).toMatchObject({ severity: 0 });
});

test("the board takes no event filters", () => {
  // Those belong to the updates tab, which is its own route. A board
  // filtered by `phase` would send the API a parameter it refuses.
  expect(boardSearch({ kind: "incident", phase: "open" })).toEqual({});
});

test("an unknown filter value falls back rather than erroring", () => {
  // A stale bookmark or a typo must not leave a blank screen.
  expect(updatesSearch({ kind: "nonsense" })).toMatchObject({
    kind: "incident",
  });
});

test("a filter nobody set stays unset", () => {
  // An absent filter and a defaulted one are different requests. The
  // first asks for everything.
  expect(updatesSearch({}).kind).toBeUndefined();
});

test("discover takes a query and a severity, and has no tabs", () => {
  // The spec gives Discover one body. A tab schema here would let a
  // URL name a tab the screen does not have.
  expect(discoverSearch({ q: " redis ", severity: "4" })).toEqual({
    q: "redis",
    severity: 4,
  });
});

test("a service's components tab takes tracking, its updates tab does not", () => {
  expect(serviceComponentsSearch({ tracking: "tracked" })).toMatchObject({
    tracking: "tracked",
  });
  expect(componentUpdatesSearch({ tracking: "tracked" })).toEqual({});
});
