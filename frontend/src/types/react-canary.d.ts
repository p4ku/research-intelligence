// Next bundles a React canary that exports <ViewTransition> (used for the
// skeleton → content handoff on streamed sections); @types/react ships its
// declaration behind this reference (node_modules/@types/react/canary.d.ts).
// Do not convert to `import 'react/canary'` — verbatimModuleSyntax would emit
// a runtime import of a module that does not exist.
/// <reference types="react/canary" />
