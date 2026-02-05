<?php
// ================================
// 1. DATABASE CONNECTION
// ================================
$host = '127.0.0.1';
$db = 'medication_tracker';
$user = 'med_user';
$pass = '';

try {
    $pdo = new PDO(
        "mysql:host=$host;dbname=$db;charset=utf8mb4",
        $user,
        $pass,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (PDOException $e) {
    http_response_code(500);
    die("DB Error");
}

// ================================
// 2. API MODE (Raspberry Pi)
// ================================
if (
    $_SERVER['REQUEST_METHOD'] === 'POST' &&
    isset($_SERVER['CONTENT_TYPE']) &&
    str_contains($_SERVER['CONTENT_TYPE'], 'application/json')
) {
    header('Content-Type: application/json');

    // API key check
    $headers = getallheaders();
    if (!isset($headers['X-API-KEY']) || $headers['X-API-KEY'] !== 'SECRET123') {
        http_response_code(403);
        echo json_encode(['status' => 'error', 'msg' => 'Unauthorized']);
        exit;
    }

    $input = json_decode(file_get_contents("php://input"), true);
    if (!$input || !isset($input['box_id'], $input['dispensed'])) {
        http_response_code(400);
        echo json_encode(['status' => 'error', 'msg' => 'Bad request']);
        exit;
    }

    try {
        $sql = "UPDATE medications
                SET total_pills = GREATEST(total_pills - ?, 0)
                WHERE box_id = ?";
        $stmt = $pdo->prepare($sql);
        $stmt->execute([
            (int)$input['dispensed'],
            (int)$input['box_id']
        ]);

        echo json_encode([
            'status' => 'success',
            'box_id' => (int)$input['box_id']
        ]);
    } catch (PDOException $e) {
        http_response_code(500);
        echo json_encode(['status' => 'error']);
    }

    exit; // STOP HTML OUTPUT
}

// ================================
// 3. NORMAL DASHBOARD LOGIC
// ================================
$msg = "";

// 2. LOGIC: ADD MEDICATION
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['add_med'])) {
    try {
        // schedule_time_2 is NULL if only 1 dose per day is chosen
        $t2 = ($_POST['times_per_day'] == "2") ? $_POST['t2'] : null;

        $sql = "INSERT INTO medications (box_id, medication_id, medication_name, total_pills, pills_per_intake, schedule_time_1, schedule_time_2)
                VALUES (?, ?, ?, ?, ?, ?, ?)";
        $pdo->prepare($sql)->execute([
            $_POST['box_id'],
            $_POST['med_id'],
            $_POST['name'],
            $_POST['total'] ?? 0,
            $_POST['per_intake'], // How many pills fall per dispense
            $_POST['t1'],
            $t2
        ]);
        $msg = "Medication added successfully to Box #" . $_POST['box_id'];
    } catch (PDOException $e) {
        $msg = "Error: Box #" . $_POST['box_id'] . " is already occupied.";
    }
}

// 3. LOGIC: UPDATE MEDICATION
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['update_med'])) {
    try {
        $t2 = ($_POST['times_per_day'] == "2") ? $_POST['t2'] : null;

        $sql = "UPDATE medications
                SET medication_name = ?, total_pills = ?, pills_per_intake = ?, schedule_time_1 = ?, schedule_time_2 = ?
                WHERE box_id = ?";
        $pdo->prepare($sql)->execute([
            $_POST['name'],
            $_POST['total'],
            $_POST['per_intake'],
            $_POST['t1'],
            $t2,
            $_POST['box_id']
        ]);
        $msg = "Box #" . $_POST['box_id'] . " settings updated.";
    } catch (PDOException $e) {
        $msg = "Update failed: " . $e->getMessage();
    }
}

// 4. LOGIC: DELETE
if (isset($_GET['delete'])) {
    $pdo->prepare("DELETE FROM medications WHERE box_id = ?")->execute([$_GET['delete']]);
    $msg = "Record deleted.";
}

// 5. FETCH DATA FOR TABLE
$query = "SELECT *,
          TIME_FORMAT(schedule_time_1, '%H:%i') as t1,
          TIME_FORMAT(schedule_time_2, '%H:%i') as t2
          FROM medications
          ORDER BY box_id ASC";
$data = $pdo->query($query)->fetchAll(PDO::FETCH_ASSOC);

// 6. CHECK FOR LOW STOCK ALERTS
$lowStockThreshold = 10; // Alert when 10 or fewer pills remain
$criticalStockThreshold = 5; // Critical alert when 5 or fewer pills remain
$alerts = [];

foreach ($data as $row) {
    if ($row['total_pills'] <= $criticalStockThreshold && $row['total_pills'] > 0) {
        $alerts[] = [
            'type' => 'critical',
            'box' => $row['box_id'],
            'name' => $row['medication_name'],
            'count' => $row['total_pills']
        ];
    } elseif ($row['total_pills'] <= $lowStockThreshold && $row['total_pills'] > 0) {
        $alerts[] = [
            'type' => 'warning',
            'box' => $row['box_id'],
            'name' => $row['medication_name'],
            'count' => $row['total_pills']
        ];
    } elseif ($row['total_pills'] == 0) {
        $alerts[] = [
            'type' => 'empty',
            'box' => $row['box_id'],
            'name' => $row['medication_name'],
            'count' => 0
        ];
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Pill Dispenser Dashboard</title>
    <style>
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #f4f7f6;
            padding: 20px;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        h2 {
            color: #2c3e50;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
        }
        th, td {
            padding: 12px;
            border-bottom: 1px solid #eee;
            text-align: left;
        }
        th {
            background: #f8f9fa;
        }
        input, select {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 5px;
            cursor: pointer;
        }
        .btn-save {
            background: #27ae60;
        }
        .msg {
            padding: 10px;
            background: #dff0d8;
            color: #3c763d;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .hidden {
            display: none;
        }

        /* ALERT STYLES */
        .alert-container {
            margin-bottom: 20px;
        }
        .alert {
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .alert-warning {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            color: #856404;
        }
        .alert-critical {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            color: #721c24;
        }
        .alert-empty {
            background: #e2e3e5;
            border-left: 4px solid #6c757d;
            color: #383d41;
        }
        .alert-icon {
            font-size: 24px;
            font-weight: bold;
        }
        .alert-content {
            flex: 1;
        }
        .alert-title {
            font-weight: bold;
            margin-bottom: 3px;
        }
        .alert-message {
            font-size: 14px;
        }
        .stock-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 5px;
        }
        .stock-low {
            background: #fff3cd;
            color: #856404;
        }
        .stock-critical {
            background: #f8d7da;
            color: #721c24;
        }
        .stock-empty {
            background: #e2e3e5;
            color: #383d41;
        }
        .stock-ok {
            background: #d4edda;
            color: #155724;
        }
    </style>
</head>
<body>
    <h1>💊 Medication Dispenser Dashboard</h1>

    <?php if($msg): ?>
        <div class="msg"><?= $msg ?></div>
    <?php endif; ?>

    <!-- LOW STOCK ALERTS -->
    <?php if(count($alerts) > 0): ?>
        <div class="alert-container">
            <?php foreach($alerts as $alert): ?>
                <?php if($alert['type'] == 'empty'): ?>
                    <div class="alert alert-empty">
                        <div class="alert-icon">⚫</div>
                        <div class="alert-content">
                            <div class="alert-title">Box <?= $alert['box'] ?> is Empty</div>
                            <div class="alert-message"><?= htmlspecialchars($alert['name']) ?> - Refill immediately!</div>
                        </div>
                    </div>
                <?php elseif($alert['type'] == 'critical'): ?>
                    <div class="alert alert-critical">
                        <div class="alert-icon">🔴</div>
                        <div class="alert-content">
                            <div class="alert-title">Critical Stock Alert - Box <?= $alert['box'] ?></div>
                            <div class="alert-message"><?= htmlspecialchars($alert['name']) ?> - Only <?= $alert['count'] ?> pills remaining</div>
                        </div>
                    </div>
                <?php else: ?>
                    <div class="alert alert-warning">
                        <div class="alert-icon">⚠️</div>
                        <div class="alert-content">
                            <div class="alert-title">Low Stock Warning - Box <?= $alert['box'] ?></div>
                            <div class="alert-message"><?= htmlspecialchars($alert['name']) ?> - <?= $alert['count'] ?> pills remaining</div>
                        </div>
                    </div>
                <?php endif; ?>
            <?php endforeach; ?>
        </div>
    <?php endif; ?>

    <!-- ADD FORM -->
    <div class="card">
        <h3>Add Medication to Box</h3>
        <form method="POST">
            <select name="box_id" required>
                <option value="">Select Box</option>
                <option value="1">Box 1</option>
                <option value="2">Box 2</option>
                <option value="3">Box 3</option>
            </select>

            <input type="text" name="name" placeholder="Medication Name" required>
            <input type="number" name="med_id" placeholder="Med ID" required style="width:70px">
            <input type="number" name="total" placeholder="Total Stock" style="width:90px">

            <label>Pills / Dose:</label>
            <input type="number" name="per_intake" value="1" min="1" max="5" style="width:50px">

            <label>Frequency:</label>
            <select name="times_per_day" onchange="toggleAddTimes(this.value)">
                <option value="1">1x Per Day</option>
                <option value="2">2x Per Day</option>
            </select>

            <input type="time" name="t1" value="08:00">
            <span id="add_t2_span" class="hidden">
                & <input type="time" name="t2" value="20:00">
            </span>

            <button type="submit" name="add_med" class="btn">Add to System</button>
        </form>
    </div>

    <!-- DATA TABLE -->
    <div class="card">
        <table>
            <thead>
                <tr>
                    <th>Box #</th>
                    <th>Medication Name</th>
                    <th>Pills / Dose</th>
                    <th>Inventory</th>
                    <th>Daily Schedule</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($data as $row): ?>
                    <tr>
                        <form method="POST">
                            <input type="hidden" name="box_id" value="<?= $row['box_id'] ?>">

                            <td><strong>Box <?= $row['box_id'] ?></strong></td>

                            <td>
                                <input type="text" name="name" value="<?= htmlspecialchars($row['medication_name']) ?>">
                            </td>

                            <td>
                                <input type="number" name="per_intake" value="<?= $row['pills_per_intake'] ?>" style="width:50px">
                            </td>

                            <td>
                                <input type="number" name="total" value="<?= $row['total_pills'] ?>" style="width:70px">
                                <?php
                                    $pills = $row['total_pills'];
                                    if ($pills == 0) {
                                        echo '<span class="stock-badge stock-empty">EMPTY</span>';
                                    } elseif ($pills <= 5) {
                                        echo '<span class="stock-badge stock-critical">CRITICAL</span>';
                                    } elseif ($pills <= 10) {
                                        echo '<span class="stock-badge stock-low">LOW</span>';
                                    } else {
                                        echo '<span class="stock-badge stock-ok">OK</span>';
                                    }
                                ?>
                            </td>

                            <td>
                                <select name="times_per_day" onchange="toggleRowTimes(this)">
                                    <option value="1" <?= $row['t2'] ? '' : 'selected' ?>>1x / Day</option>
                                    <option value="2" <?= $row['t2'] ? 'selected' : '' ?>>2x / Day</option>
                                </select>
                                <input type="time" name="t1" value="<?= $row['t1'] ?>">
                                <input type="time" name="t2" value="<?= $row['t2'] ?>"
                                       class="<?= $row['t2'] ? '' : 'hidden' ?>"
                                       style="display: <?= $row['t2'] ? 'inline-block' : 'none' ?>;">
                            </td>

                            <td>
                                <button type="submit" name="update_med" class="btn btn-save">Update</button>
                                <a href="?delete=<?= $row['box_id'] ?>"
                                   onclick="return confirm('Remove medication?')"
                                   style="color:red; margin-left:10px;">Delete</a>
                            </td>
                        </form>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <script>
        function toggleAddTimes(val) {
            document.getElementById('add_t2_span').style.display = (val == "2") ? 'inline' : 'none';
        }

        function toggleRowTimes(el) {
            const row = el.closest('tr');
            const t2 = row.querySelector('input[name="t2"]');
            t2.style.display = (el.value == "2") ? 'inline-block' : 'none';
        }
    </script>
</body>
</html>
