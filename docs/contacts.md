# Contacts API Documentation

This document provides comprehensive documentation for the Contacts API endpoints, including how to use pagination, sorting, and search functionality.

## Base URL
All endpoints are relative to your API's base URL (e.g., `https://api.example.com/api`).

## Authentication
All endpoints require authentication using JWT tokens. Include the token in the `Authorization` header:
```
Authorization: Bearer your.jwt.token.here
```

---

## List Contacts

### `GET /contacts/`

Returns a paginated list of contacts with optional filtering and sorting.

### Query Parameters

| Parameter  | Type   | Required | Default     | Description |
|------------|--------|----------|-------------|-------------|
| limit      | int    | No       | 100         | Number of results to return per page |
| offset     | int    | No       | 0           | Number of items to skip |
| search     | string | No       | -           | Search term to filter contacts |
| sort_by    | string | No       | display_name| Field to sort by (see below) |
| sort_order | string | No       | asc         | Sort order: 'asc' or 'desc' |

### Sortable Fields
- `display_name` (default)
- `first_name`
- `last_name`
- `email`
- `created_at`
- `updated_at`

### Search Behavior
When using the `search` parameter, the API performs a case-insensitive search across these fields with the following weights:
1. `display_name` (highest weight)
2. `first_name`
3. `last_name`
4. `email`
5. `notes` (lowest weight)

Search uses AND logic for multiple terms. For example, searching for "john smith" will match contacts that contain both "john" and "smith" in any of the searchable fields.

### Response Format

```json
{
  "items": [
    {
      "display_name": "John Doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "phone": "+1234567890",
      "location": "New York, USA",
      "avatar_path": "/media/avatars/john_doe.jpg",
      "created_at": "2023-01-01T12:00:00Z",
      "updated_at": "2023-01-01T12:00:00Z"
    }
  ],
  "count": 1
}
```

### Pagination

The response includes a `count` field with the total number of items. Use the `limit` and `offset` parameters to implement pagination in your frontend:

```
# First page (items 1-10)
GET /contacts/?limit=10&offset=0

# Second page (items 11-20)
GET /contacts/?limit=10&offset=10
```

### Examples

1. Basic listing with default sorting:
   ```
   GET /contacts/
   ```

2. Search for contacts with "john" in any field:
   ```
   GET /contacts/?search=john
   ```

3. Sort by creation date (newest first):
   ```
   GET /contacts/?sort_by=created_at&sort_order=desc
   ```

4. Search with pagination and sorting:
   ```
   GET /contacts/?search=john&sort_by=last_name&sort_order=asc&limit=20&offset=40
   ```

---

## Common Response Status Codes

- `200 OK`: Request successful
- `400 Bad Request`: Invalid parameters
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Not enough permissions
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

## Rate Limiting

API requests are rate limited to prevent abuse. If you exceed the limit, you'll receive a `429 Too Many Requests` response with a `Retry-After` header indicating when you can try again.

---

## Notes

- All timestamps are in UTC
- String fields are case-insensitive for search but maintain their original case in responses
- Empty or null values are omitted from the response
- The API follows RESTful conventions and uses standard HTTP methods and status codes
