
# PromoteDeterministicNextCheckRequest

Deterministic next-check promotion request

## Properties

Name | Type
------------ | -------------
`clusterLabel` | string
`context` | string
`description` | string
`evidenceNeeded` | Array&lt;any&gt;
`method` | string
`priorityScore` | number
`topProblem` | string
`urgency` | string
`whyNow` | string
`workstream` | string

## Example

```typescript
import type { PromoteDeterministicNextCheckRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "clusterLabel": null,
  "context": null,
  "description": null,
  "evidenceNeeded": null,
  "method": null,
  "priorityScore": null,
  "topProblem": null,
  "urgency": null,
  "whyNow": null,
  "workstream": null,
} satisfies PromoteDeterministicNextCheckRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PromoteDeterministicNextCheckRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
