
# RecordNextCheckUsefulnessRequest

Usefulness feedback request

## Properties

Name | Type
------------ | -------------
`artifactPath` | string
`judgmentScope` | string
`problemClass` | string
`reviewStage` | string
`reviewerConfidence` | string
`usefulnessClass` | string
`usefulnessSummary` | string
`workstream` | string

## Example

```typescript
import type { RecordNextCheckUsefulnessRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "artifactPath": null,
  "judgmentScope": null,
  "problemClass": null,
  "reviewStage": null,
  "reviewerConfidence": null,
  "usefulnessClass": null,
  "usefulnessSummary": null,
  "workstream": null,
} satisfies RecordNextCheckUsefulnessRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RecordNextCheckUsefulnessRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
