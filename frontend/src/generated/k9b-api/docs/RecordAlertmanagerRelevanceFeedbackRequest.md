
# RecordAlertmanagerRelevanceFeedbackRequest

AlertManager relevance feedback request

## Properties

Name | Type
------------ | -------------
`alertmanagerRelevance` | string
`alertmanagerRelevanceSummary` | string
`artifactPath` | string

## Example

```typescript
import type { RecordAlertmanagerRelevanceFeedbackRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "alertmanagerRelevance": null,
  "alertmanagerRelevanceSummary": null,
  "artifactPath": null,
} satisfies RecordAlertmanagerRelevanceFeedbackRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RecordAlertmanagerRelevanceFeedbackRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


