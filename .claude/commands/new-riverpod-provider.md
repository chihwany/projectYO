# 새 Riverpod Provider 생성

`$ARGUMENTS` 이름의 AsyncNotifierProvider를 `mobile/lib/providers/{name}_provider.dart`에 생성하라.

## 이 프로젝트 표준 패턴

```dart
// mobile/lib/providers/{name}_provider.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../services/api_service.dart';
import '../models/{name}.dart';

part '{name}_provider.g.dart';

@riverpod
class {Name}Notifier extends _${Name}Notifier {
  @override
  Future<List<{Model}>> build() async {
    return _fetch();
  }

  Future<List<{Model}>> _fetch() async {
    return ref.read(apiServiceProvider).get{Name}List();
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_fetch);
  }
}
```

## 상태 종류별 패턴 선택

### 목록 조회 (List)
```dart
@riverpod
class {Name}List extends _${Name}List {
  @override
  Future<List<{Model}>> build() async {
    return ref.read(apiServiceProvider).get{Name}List();
  }
}
```

### 단건 조회 (Detail) — ID 파라미터 필요
```dart
@riverpod
class {Name}Detail extends _${Name}Detail {
  @override
  Future<{Model}> build(String id) async {
    return ref.read(apiServiceProvider).get{Name}(id);
  }
}
```

### 검색 결과 (Search) — 파라미터 변경 시 자동 갱신
```dart
@riverpod
class SearchResults extends _$SearchResults {
  @override
  Future<List<Product>> build({
    required String keyword,
    required String platform,
  }) async {
    return ref.read(apiServiceProvider).search(keyword: keyword, platform: platform);
  }
}
```

### 단순 상태 관리 (UI State — 로딩 없음)
```dart
@riverpod
class {Name}Filter extends _${Name}Filter {
  @override
  String build() => '';  // 초기값

  void update(String value) => state = value;
}
```

## CRUD 작업 포함 패턴 (키워드 관리 등)

```dart
@riverpod
class Keywords extends _$Keywords {
  @override
  Future<List<Keyword>> build() async {
    return ref.read(apiServiceProvider).getKeywords();
  }

  Future<void> add(KeywordCreate data) async {
    await ref.read(apiServiceProvider).createKeyword(data);
    ref.invalidateSelf();  // 목록 새로고침
  }

  Future<void> delete(String id) async {
    await ref.read(apiServiceProvider).deleteKeyword(id);
    ref.invalidateSelf();
  }

  Future<void> toggle(String id) async {
    await ref.read(apiServiceProvider).toggleKeyword(id);
    ref.invalidateSelf();
  }
}
```

## freezed 모델이 없는 경우

반환 타입이 아직 없다면 `mobile/lib/models/{name}.dart`도 함께 생성:
```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part '{name}.freezed.dart';
part '{name}.g.dart';

@freezed
class {Name} with _${Name} {
  const factory {Name}({
    required String id,
    required String title,
    // ...
  }) = _{Name};

  factory {Name}.fromJson(Map<String, dynamic> json) => _${Name}FromJson(json);
}
```

## 코드 생성 명령어

파일 생성 후 반드시 실행:
```bash
cd mobile
dart run build_runner build --delete-conflicting-outputs
```
