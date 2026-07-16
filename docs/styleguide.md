# Principles for Clean Django and Python

*A practical style guide inspired by functional programming while embracing
Django's strengths.*

## Philosophy

Write Python as if clarity is the primary feature.

Django provides a strong application platform: routing, validation,
authentication, persistence, transactions, and operational conventions. Use
those strengths deliberately. Application code should make the domain and its
workflows easy to see.

Optimize for the person reading the code in five years—quite possibly
yourself.

These principles are strong defaults, not laws. Depart from them when the
alternative is demonstrably clearer, safer, or better aligned with Django.

## 1. Prefer functions over stateless classes

If something does not have meaningful identity, configuration, or lifecycle,
make it a function. Use modules as namespaces.

```python
# planning/operations.py

def add_stop(*, tour: Tour, gallery: Gallery, actor: User) -> TourStop:
    ...
```

Avoid service classes that exist only to group methods:

```python
TourService().add_stop(...)
```

Prefer the module and function directly:

```python
planning.operations.add_stop(...)
```

## 2. Use classes for things with a reason to be classes

Classes are appropriate for:

- Domain entities and value objects
- Configuration with meaningful structure
- Resources with state or lifecycle
- Protocol implementations and interchangeable strategies
- Framework APIs that expect classes

Do not create classes merely to organize functions or imitate dependency
injection frameworks from other ecosystems.

## 3. Prefer immutable values where they clarify intent

Use frozen dataclasses for meaningful domain values:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TourWindow:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if self.ends_at <= self.starts_at:
            raise ValueError("A tour must end after it starts.")
```

Prefer `tuple` and `frozenset` when a collection is not intended to change.
Aim to make invalid states difficult to construct.

Do not wrap every primitive or request payload in a custom value object.
Pydantic schemas are often sufficient at application boundaries, and plain
types are appropriate when they remain unambiguous.

## 4. Type public boundaries

Type public functions, application operations, query functions, task inputs,
and integration boundaries. Run mypy or Pyright in CI.

```python
def publish_exhibition(
    *,
    exhibition_id: int,
    actor: User,
) -> PublishResult:
    ...
```

Type hints are architecture documentation, but they do not replace runtime
validation or database constraints.

## 5. Prefer composition over inheritance

Use inheritance for genuine "is-a" relationships and framework extension
points. Prefer functions, composition, or `Protocol` for reuse and
substitution. Avoid deep inheritance trees and mixins with surprising side
effects.

## 6. Make business operations explicit

Core workflows should live in named application functions whose call sites
tell the story:

```python
planning.operations.complete_tour(tour=tour, actor=request.user)
```

Avoid hiding important behavior inside:

- Model `save()` overrides
- Signals
- Middleware
- Decorators with side effects
- Framework hooks unrelated to the use-case

A reader should be able to follow a write from the API boundary to its
authorization, transaction, persistence, and scheduled side effects.

## 7. Treat Django models as persistence-backed domain objects

Django models are not merely database records, but they should not become
workflow coordinators either.

Good model behavior is local and primarily concerned with the instance's own
state:

```python
exhibition.is_open_on(day)
export_job.is_expired
contact.display_label
```

Operations involving several models, authorization context, transactions, or
external systems belong in application functions.

Be cautious with methods such as `tour.is_editable_by(user)`: they can hide
database queries and tenant-aware policy. Prefer an explicit policy function
when authorization depends on broader context:

```python
planning.policies.can_edit_tour(actor=user, tour=tour)
```

## 8. Keep persistence deliberate

It is fine for application operations and query functions to use the Django
ORM directly. A repository layer is not required merely to hide the ORM.

Keep database access in predictable places. Avoid scattering ORM queries
through serializers, schema properties, templates, and unrelated helper
functions. Make query cost visible and use `select_related`, `prefetch_related`,
annotations, and indexes deliberately.

## 9. Separate commands from queries when complexity warrants it

Functions that change state are commands or operations. Functions that read
data are queries. Keeping them conceptually separate makes authorization,
transactions, caching, and performance easier to reason about.

For a substantial application area:

```text
planning/
    operations.py
    queries.py
```

A small app does not need this structure immediately; `services.py` may be
clearer until read and write paths become substantial. This principle does not
require separate data models or full CQRS.

## 10. Make transaction boundaries explicit

Wrap a complete database use-case in `transaction.atomic()`, rather than
placing unrelated atomic blocks around tiny helpers.

Use row locks or conditional updates when correctness depends on current
state:

```python
@transaction.atomic
def accept_invitation(*, invitation_id: int, actor: User) -> Membership:
    invitation = Invitation.objects.select_for_update().get(id=invitation_id)
    ...
```

Keep transaction scope focused. Do not hold database locks while performing
slow network requests.

## 11. Distinguish database commits from external side effects

`transaction.atomic()` only governs the database. It cannot atomically include
email, object storage, Celery publication, or third-party APIs.

Schedule non-database work after a successful commit:

```python
transaction.on_commit(lambda: send_receipt.delay(order.id))
```

Use an outbox when a side effect must be durably scheduled despite a process
failure between the database commit and task publication.

Assume external delivery is at least once. Give tasks and integrations stable
idempotency keys where duplicate execution would matter.

## 12. Put invariants at the lowest reliable layer

Use several layers for different responsibilities:

- Schemas validate and normalize untrusted input.
- Operations enforce workflow and authorization rules.
- Models express local behavior.
- Database constraints protect durable invariants under every code path.

Use unique, check, foreign-key, and exclusion constraints whenever the
database can express the rule. Application-level checks improve error
messages, but they do not protect against races.

## 13. Design writes for concurrency and retries

Assume that two requests, workers, or retries can execute the same operation
at the same time.

Prefer:

- Database constraints as the final authority
- `select_for_update()` when a workflow must be serialized
- Conditional updates when state transitions can be expressed atomically
- Bounded retries for expected uniqueness conflicts
- Idempotency records for retried API operations
- Resumable background jobs with explicit state transitions

A preceding `exists()` query is not a uniqueness guarantee. Catch expected
constraint failures and translate them into a controlled domain or API error.

## 14. Keep signals out of the critical path

Do not make correctness depend exclusively on Django signals. Signals are
easy to bypass with bulk mutations and can make execution paths difficult to
discover.

Signals can be useful for secondary infrastructure concerns such as:

- Defense-in-depth file cleanup
- Opportunistic cache invalidation
- Metrics
- Search indexing

Critical ownership, authorization, session, financial, and cross-aggregate
rules should use explicit operations and database enforcement. If a signal is
used, test that it is registered in production and document mutation paths
that bypass it.

## 15. Pass dependencies explicitly where it provides leverage

Explicit collaborators are especially valuable at external boundaries:

- Email delivery
- Object storage
- Payment and other third-party APIs
- Clocks when behavior depends on time
- Randomness and token generation when deterministic tests matter

Direct imports of stable Django infrastructure and application models are
usually clear and appropriate. Avoid passing every setting, logger, manager,
and ORM dependency through every function merely to satisfy a dependency
injection pattern.

## 16. Keep functions small enough to tell one coherent story

Prefer one level of abstraction per function. Split a function when its
responsibilities diverge, when a concept deserves a name, or when isolation
materially improves testing.

Do not split code simply to satisfy an arbitrary line count. A readable
40-line use-case is often clearer than ten tiny helpers that require jumping
between files.

## 17. Minimize surprising framework behavior

Django's conventions and framework mechanisms are useful. Use them where they
make behavior more standard and legible; avoid using them to conceal domain
workflows.

Decorators, middleware, signals, managers, and hooks should have narrow,
documented responsibilities. Security-sensitive behavior should be explicit,
auditable, and covered by tests.

## 18. Optimize for safe change

Before adding an abstraction, ask:

- Will its purpose be obvious in five years?
- Can it be renamed or moved without hidden behavior changing?
- Is its execution path discoverable?
- Are its transaction and side-effect boundaries visible?
- Does the database protect its durable invariants?
- What happens if it runs twice or concurrently?

If the answers are unclear, simplify the design or make the missing guarantee
explicit.

## Practical application structure

Use the smallest structure that keeps responsibilities clear. A mature app may
look like this:

```text
planning/
    api.py          # HTTP parsing, authentication, response mapping
    schemas.py      # Boundary validation and serialization
    models.py       # Persistence and local model behavior
    operations.py   # Authorized, transactional write use-cases
    queries.py      # Deliberate read paths and query shaping
    policies.py     # Context-dependent authorization decisions
    tasks.py        # Idempotent background entry points
```

Not every app needs every module. Create a module when it gives a coherent
concept a clear home, not to satisfy a template.

## Guiding principle

Django provides the platform. Python expresses the application.

Architecture should make business behavior explicit, predictable, safe under
failure and concurrency, and easy to change.

The goal is not to imitate Elixir. The goal is to bring the same virtues into
idiomatic Python and Django:

- Explicit over implicit
- Functions over unnecessary objects
- Composition over inheritance
- Immutable values where useful
- Visible control flow
- Deliberate persistence
- Clear transaction and side-effect boundaries
- Database-enforced invariants
- Concurrency-safe, idempotent writes
- Small, coherent modules
